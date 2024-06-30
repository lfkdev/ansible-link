- Added install script

#### **Thread Safety** 🔒
- Jobs are now also being saved to disk
- `/jobs` endpoint now pulls all infos from saved JSON files
- (potentially **BREAKING**) saved jobs now only use their UUID as name (`jq` can be used to filter easily)

#### **WSGI** 🌐
- Minor import refactor
- WSGI default file
- changed README for gunicorn