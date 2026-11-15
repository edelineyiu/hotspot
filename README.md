# Global Fire Hotspot Viewer

This Flask site requests one selected date of global MODIS and VIIRS hotspot
records from NASA FIRMS. It shows daily counts and a color-coded map. It does
not download the entire archive in advance.

The date picker starts at 2000-11-01, the earliest MODIS period used here.
VIIRS products start later; the app omits products before their data begins.
Hotspot counts are satellite detections, not confirmed individual fires or
burned-area boundaries.

## Run locally

1. Install Python dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your FIRMS key. The `.env` file is
   ignored by Git. Then start the app:

   ```powershell
   python .\web
   ```

3. Open `http://127.0.0.1:5000`.
   The main page and the linked world report both load every MODIS and VIIRS
   detection returned for the selected date.

The map uses NASA EOSDIS GIBS and Leaflet from public web services, so the
browser needs an internet connection.

Run the focused checks with:

```powershell
python -m unittest discover -s tests
```

## Deploy to Render

1. Push the project files to a Git repository. Do not commit `.env` or any API
   key; `.gitignore` excludes `.env`.
2. In Render, create a **Blueprint** from that repository. Render reads
   `render.yaml` and creates the web service.
3. In the Render service's environment settings, add `FIRMS_MAP_KEY`. Enter
   the value there; never put it in browser code or source files.
4. Open the Render service URL after deployment completes.

The public app applies basic in-memory per-IP request limits. These limits
reset when the service restarts and are not a substitute for account-level
usage limits. Monitor API usage in the FIRMS dashboard.
