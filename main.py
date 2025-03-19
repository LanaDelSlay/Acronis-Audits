import requests
import datetime
import json
import pyperclip

limit = 250 ## This is how many rows we can receive, acronis can handle up to 50k. Change to what you need
threshold_days = 6 ## How many days should lapse til we consider it out of date. 

with open('api_key.json') as f:
    data = json.load(f)

CLIENT_ID = data['CLIENT_ID']
CLIENT_SECRET = data['SECRET_KEY']
BASE_URL = data['BASE_URL']
API_URL = f"{BASE_URL}/api/resource_management/v4/resource_statuses?type=resource.machine"
TOKEN_URL = f"{BASE_URL}/api/2/idp/token"

def get_access_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=payload)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print(f"Error fetching access token: {response.status_code} - {response.text}")
        return None

def get_managed_machines():
    access_token = get_access_token()
    if not access_token:
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    all_machines = []
    url = f"{API_URL}&limit={limit}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        all_machines.extend(data.get("items", []))

    except requests.exceptions.RequestException as e:
        print(f"Error fetching resources: {e}")
        return []
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error processing response: {e}")
        return []

    return all_machines
def check_out_of_sync_machines():
    machines = get_managed_machines()
    out_of_sync_machines = []
    now = datetime.datetime.now(datetime.UTC)

    for machine in machines:
        last_backup = None
        for policy in machine.get("policies", []):
            if policy.get("type") == "policy.backup.machine" and policy.get("last_success_run"):
                last_backup = policy.get("last_success_run")
                break

        if last_backup:
            try:
                last_backup_time = datetime.datetime.fromisoformat(last_backup.replace("Z", "+00:00"))
                days_since_last_backup = (now - last_backup_time).days

                if days_since_last_backup >= threshold_days:
                    out_of_sync_machines.append({
                        "id": machine.get("context", {}).get("id"),
                        "name": machine.get("context", {}).get("name"),
                        "last_backup": last_backup_time.isoformat(),
                        "days_out_of_sync": days_since_last_backup,
                        "tenant_name": machine.get("context", {}).get("tenant_name", {})
                    })
            except (ValueError, TypeError) as e:
                print(f"Error parsing date {last_backup} for machine {machine.get('context', {}).get('id')}: {e}")
            except KeyError as e:
                print (f"Missing Key whilst processing data: {e}")
        else: #Handles machines with no backups
            print(f"Machine {machine.get('context', {}).get('user_defined_name', 'UNKNOWN ID')} has no last successful backup.")
            out_of_sync_machines.append({
                "id": machine.get("context", {}).get("id", "UNKNOWN ID"),
                "name": machine.get("context", {}).get("name", "UNKNOWN NAME"),
                "last_backup": None,
                "days_out_of_sync": None,
                "tenant_name": machine.get("context", {}).get("tenant_name", {})
            })

    return out_of_sync_machines

if __name__ == "__main__":
    pyperclip.copy(get_managed_machines())
    out_of_sync = check_out_of_sync_machines()

    if out_of_sync:
        # 1. Sort by tenant_name, then by machine name
        out_of_sync.sort(key=lambda machine: (machine["tenant_name"], machine["name"]))

        print("Machines out of sync for " + str(threshold_days) + " or more days (or with no backup):")

        # 2. Group by tenant_name and print
        current_tenant = None
        timeFormatted = None
        for machine in out_of_sync:
            if machine["tenant_name"] != current_tenant:
                current_tenant = machine["tenant_name"]
                print(f"\nTenant: {current_tenant}") 
            if machine['last_backup'] != None:
                dt = datetime.datetime.fromisoformat(machine['last_backup'].replace("Z", "+00:00")) # Convert ISO 8601 to datetime compatible format
                timeFormatted = dt.strftime("%m/%d/%Y")
            else:
                timeFormatted = machine["last_backup"]
            print(f"    Name: {machine['name']}, Last Backup: {timeFormatted}, Days Out of Sync: {machine['days_out_of_sync']}")
    else:
        print("All machines are up to date.")