import requests

response = requests.get(
    "https://api2.openreview.net/pdf/1",
    headers={"Accept":"*/*"},
)

data = response.json()