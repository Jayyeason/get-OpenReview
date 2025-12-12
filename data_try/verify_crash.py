import openreview
import json

client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')
NOTE_ID = 'YEV6nMpZrg'

try:
    edits = client.get_note_edits(note_id=NOTE_ID)
except AttributeError:
    edits = client.get_edits(note_id=NOTE_ID)

if edits:
    edit = edits[0]
    # Simulate the code: edits_data = [vars(edit).copy() for edit in edits]
    data = vars(edit).copy()
    
    print("Testing json.dump on vars(edit)...")
    try:
        json.dumps(data)
        print("Success!")
    except TypeError as e:
        print(f"Failed as expected: {e}")
