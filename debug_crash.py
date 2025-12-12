import openreview
import os
import sys

VENUE_ID = "ICLR.cc/2025/Conference"
BASEURL = "https://api2.openreview.net"
FORUM_ID = "zxg6601zoc"

client = openreview.api.OpenReviewClient(baseurl=BASEURL)

print(f"Fetching forum {FORUM_ID}...")
try:
    # Get the submission note
    # We use get_note assuming we know the id, but usually we iterate.
    # get_all_notes returns a list.
    # Let's try to get the specific note by id if possible, or filter.
    # get_note(id)
    submission = client.get_note(FORUM_ID)
    
    # We need to simulate how the main script gets it: get_all_notes with details='replies'
    # But get_note doesn't support details='replies' in the same way? 
    # Actually client.get_note(id, details='replies') might work if the API supports it.
    # But the script uses get_all_notes.
    
    # Let's try to fetch it the way the script does, but filtering for this forum.
    # get_all_notes(invitation=..., details='replies')
    # Since we can't filter by id in get_all_notes easily without fetching all?
    # Actually we can use 'id' parameter if supported? No.
    
    # But wait, client.get_note(id) usually returns the note.
    # To get details='replies', we might need to fetch replies separately if get_note doesn't do it.
    # However, the script uses:
    # client.get_all_notes(invitation=f"{VENUE_ID}/-/Submission", details="replies")
    
    # Let's try to see if we can reproduce the NoneType error with the object structure.
    
    print("Submission found.")
    print(f"ID: {submission.id}")
    
    # Check if details is present
    if not hasattr(submission, 'details'):
        print("submission.details is MISSING (as expected for simple get_note)")
        # In the script, details='replies' is passed.
        # Let's try to manually fetch replies to simulate.
        replies = client.get_notes(forum=FORUM_ID)
        # This is not exactly what details='replies' does. 
        # details='replies' attaches them to the note object.
        
    # Let's try to use the exact call but maybe we can't filter by forum easily in get_all_notes.
    # But wait, I can use client.get_notes(id=FORUM_ID, details='replies')?
    
    notes = client.get_all_notes(id=FORUM_ID, details='replies')
    if not notes:
        print("Note not found via get_all_notes")
        sys.exit(1)
        
    submission = notes[0]
    print(f"Loaded submission via get_all_notes: {submission.id}")
    
    details = getattr(submission, 'details', None)
    print(f"details type: {type(details)}")
    
    if details is None:
        print("details is None!")
    else:
        replies = details.get('replies')
        print(f"details['replies'] type: {type(replies)}")
        if replies is None:
            print("details['replies'] is None!")
        else:
            print(f"replies length: {len(replies)}")
            
            # Check for Official_Review signatures
            official_reviews = [
                r for r in replies 
                if r["invitations"][0].endswith("Official_Review")
            ]
            print(f"Official Reviews found: {len(official_reviews)}")
            
            for i, review in enumerate(official_reviews):
                sigs = review.get("signatures")
                print(f"Review {i} signatures: {sigs}")
                if sigs is None:
                    print(f"Review {i} has None signatures!")
                
                # Check edits for this review
                review_id = review['id']
                print(f"Checking edits for review {review_id}...")
                try:
                    edits = client.get_note_edits(note_id=review_id)
                    for j, edit in enumerate(edits):
                        note = edit.note
                        if note.signatures is None:
                            print(f"  Edit {j} (id={edit.id}) has None signatures!")
                        else:
                            # print(f"  Edit {j} signatures: {note.signatures}")
                            pass
                except Exception as e:
                    print(f"  Failed to get edits: {e}")

except Exception as e:
    print(f"Error: {e}")
