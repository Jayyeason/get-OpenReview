import openreview
import json
import os
from typing import List, Dict, Any
from datetime import datetime, timezone
from inspect import signature

VENUE_ID = "ICLR.cc/2025/Conference"
BASEURL = "https://api2.openreview.net"
FORUM_ID = "zmmfsJpYcq"

client = openreview.api.OpenReviewClient(baseurl=BASEURL)

def to_iso_time(ms: int) -> str:
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()

def get_review_versions(client, latest_review):
    note_id = latest_review["id"]
    print(f"\nProcessing Review ID: {note_id} (Signature: {latest_review.get('signatures')})")
    
    try:
        edits = client.get_note_edits(note_id=note_id) or []
    except Exception as e:
        print(f"[WARN] get_note_edits failed for note {note_id}: {e}")
        edits = []

    versions = []
    last_content = None

    # 1. 收集历史 Edits
    if edits:
        edits = sorted(edits, key=lambda e: e.cdate or 0)
        
        for i, edit in enumerate(edits):
            note = edit.note
            content = note.content or {}
            
            # Print edit details for debugging
            print(f"  Edit {i+1} (ID: {edit.id}):")
            print(f"    Cdate: {edit.cdate} ({to_iso_time(edit.cdate)})")
            print(f"    Signatures: {note.signatures}")
            if note.signatures is None:
                print("    [ALERT] Signatures is None!")
            
            last_content = content

            versions.append({
                "note_id": note.id,
                "replyto": latest_review["replyto"],
                "actor": "reviewer",
                "signatures": note.signatures or [], # Simulate fix
                "event_type": "review_version",
                "edit_id": edit.id,
                "version_index": len(versions) + 1,
                "time_stamp": to_iso_time(edit.cdate),
                "time_ms": edit.cdate,
                "summary": content.get("summary", {}).get("value"),
                "rating": content.get("rating", {}).get("value"),
            })

    # 2. 处理当前最新状态
    current_content = latest_review.get("content", {})
    current_time = latest_review.get("mdate", latest_review.get("cdate"))
    
    print(f"  Current State (Latest Review):")
    print(f"    Mdate/Cdate: {current_time} ({to_iso_time(current_time)})")
    print(f"    Signatures: {latest_review.get('signatures')}")
    
    if not versions or (current_content and current_content != last_content):
        versions.append({
            "note_id": note_id,
            "replyto": latest_review["replyto"],
            "actor": "reviewer",
            "signatures": latest_review.get('signatures') or [], # Simulate fix
            "event_type": "review_version",
            "edit_id": None,
            "version_index": len(versions) + 1,
            "time_stamp": to_iso_time(current_time),
            "time_ms": current_time,
            "summary": current_content.get("summary", {}).get("value"),
            "rating": current_content.get("rating", {}).get("value"),
        })
        print(f"    -> Appended as version {len(versions)}")
    else:
        print(f"    -> Skipped (Same as last edit)")

    return versions

def build_per_reviewer_chains(events):
    # Simplified version for debugging
    review_roots = [
        event for event in events
        if event.get("event_type") == "review_version"
        and event.get("version_index") == 1
    ]

    per_reviewer = {}
    note_to_reviewer = {}

    for root_review in review_roots:
        sigs = root_review.get("signatures", [])
        if not sigs:
             print(f"[WARN] Root review {root_review.get('note_id')} has NO signatures!")
             continue
             
        reviewer_id = next((s.split("/")[-1] for s in sigs if "Reviewer" in s), None)
        
        if not reviewer_id:
            print(f"[WARN] Could not extract Reviewer ID from signatures: {sigs}")
            continue
            
        per_reviewer.setdefault(reviewer_id, []).append(root_review)
        note_to_reviewer[root_review["note_id"]] = reviewer_id

    # ... (Rest of chain logic omitted for brevity as we focus on edits)
    return per_reviewer, note_to_reviewer


print(f"Fetching forum {FORUM_ID}...")
try:
    submissions = client.get_all_notes(
        forum=FORUM_ID,
        details="replies"
    )
    
    if not submissions:
        print("Submission not found!")
        exit(1)
        
    submission = submissions[0]
    details = submission.details
    
    Official_Review = [
        reply for reply in details["replies"] 
        if reply["invitations"][0].endswith("Official_Review")
    ]
    
    events = []
    for latest_review in Official_Review:
        versions = get_review_versions(client, latest_review)
        events.extend(versions)

    print("\n=== Rebuttal Chain Analysis ===")
    per_reviewer, note_to_reviewer = build_per_reviewer_chains(events)
    
    print(f"\nTotal Reviewers identified: {len(per_reviewer)}")
    for reviewer, chain in per_reviewer.items():
        print(f"  {reviewer}: {len(chain)} events (Root Note ID: {chain[0]['note_id']})")
        
    if len(per_reviewer) != len(Official_Review):
        print(f"\n[ALERT] Discrepancy! Found {len(Official_Review)} Official Reviews but only {len(per_reviewer)} chains.")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
