# TASK-027A Regressions Found

## Root Cause Analysis Complete

### Finding 1: No Live Parties (NOT A BUG)
- ✅ Parties have genuinely ended for the day
- Campus Debut party checked directly - no "Ends in" evidence
- All parties showing is_live=False correctly
- This is expected behavior at 9:51 PM EST

### Finding 2: "Party Invitations" Bug (CRITICAL)
**21 out of 26 cached parties have name="Party Invitations"**

This is a **section heading** being captured as party names.

**Evidence:**
```
[ERROR] Found 21 suspicious cache entries:
  - Party Invitations (ID: 6a61bcadd6c14ede67dd912c)
  - Party Invitations (ID: 6a61bc31d6c14efbb8dd908f)
  ... (19 more)
```

**Root Cause:**
The party discovery JavaScript in [`party/party_manager.py`](party/party_manager.py:100-283) is selecting "Party Invitations" as the party name instead of the actual party name.

**Impact:**
- Cache is polluted with invalid party objects
- Merge logic reuses these invalid names
- 21 parties have wrong names in cache

**Fix Required:**
Update party name extraction logic to:
1. Reject section headings: "Party Invitations", "Happening Now", "Shop Past Parties"
2. Ensure party name comes from the actual party card, not surrounding UI

### Finding 3: Upcoming Guideline Extraction Failing
**Upcoming parties fail to parse guidelines**

**Evidence:**
```
Campus Debut Posh Party:
- Show Posh Party Guidelines button found
- Click succeeds
- Extraction fails (modal_count: 1 but no content)
```

**Root Cause:**
The guideline extraction in [`party/party_manager.py`](party/party_manager.py:580-814) expects a modal for upcoming parties, but the content expands inline instead.

**Impact:**
- Upcoming parties have no guidelines
- Cannot determine eligibility until party goes live
- Reduces usefulness of pre-party planning

**Fix Required:**
Update `_extract_guidelines_content()` to handle inline expanded content for upcoming parties, not just modals.

## Conclusion

**The "0 live parties" result was CORRECT** - parties had ended.

**The real bugs are:**
1. ❌ "Party Invitations" section heading captured as party names (21/26 parties affected)
2. ❌ Upcoming guideline extraction failing (inline content not parsed)

These are [`party/party_manager.py`](party/party_manager.py:1) bugs, NOT share_engine issues.

## Recommended Actions

1. **Fix party name extraction** - Reject section headings
2. **Fix upcoming guideline parsing** - Handle inline expansion
3. **Clear corrupted cache** - Delete logs/party_cache.json
4. **Re-test discovery** - Verify fixes work
5. **THEN continue with share modal discovery** during live party hours

Do NOT proceed with share_engine integration until PartyManager bugs are fixed.
