# STUB — waiting for M1/M2/M3
import hashlib, json, datetime
class HashChain:
    def __init__(self, entries=None): self.entries = entries or []
    def append(self, operation, node_id, details):
        prev = self.entries[-1]["hash"] if self.entries else "GENESIS"
        payload = {"operation":operation,"node_id":node_id,"details":details,"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),"previous_hash":prev}
        payload["hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest(); self.entries.append(payload); return payload
    def verify_integrity(self):
        errors=[]; prev="GENESIS"
        for e in self.entries:
            if e.get("previous_hash") != prev: errors.append("broken previous hash")
            prev=e.get("hash")
        return (not errors, errors)
    def get_entries(self): return self.entries
