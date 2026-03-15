# Mayor Endorsement Tracker — Project Instructions

## UI Updates: Optimistic by Default

All state updates that touch the UI should be **optimistic** — update the local state immediately, fire the API call in the background, and reconcile with the server response when it arrives.

Only skip optimistic updates when there is a strong reason, such as:
- The operation is destructive and irreversible (e.g., a hard delete with no undo)
- The new state cannot be predicted without the server response (e.g., server-generated IDs or computed fields)
- A failure would leave the user in a genuinely confusing or broken state with no recovery path

In all other cases — status changes, field edits, batch operations — update the UI first.
