from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db

router = APIRouter(tags=["dashboard"])

_PAGE_STYLE = """
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 2rem;
         background: #f7f7f8; color: #1a1a1a; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .sub { color: #666; margin-bottom: 1.5rem; font-size: 0.9rem; }
  table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px;
          overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  th, td { text-align: left; padding: 0.6rem 0.9rem; border-bottom: 1px solid #eee; font-size: 0.88rem; }
  th { background: #fafafa; font-weight: 600; color: #444; }
  tr:last-child td { border-bottom: none; }
  tr.deleted { opacity: 0.45; }
  .badge { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.75rem;
           background: #eef2ff; color: #4338ca; }
  .badge.deleted { background: #fee2e2; color: #b91c1c; }
  .empty { padding: 2rem; text-align: center; color: #888; background: white; border-radius: 8px; }
  .refresh { font-size: 0.8rem; color: #888; margin-top: 1rem; }
  a { color: #4338ca; text-decoration: none; }
</style>
"""


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    patients = crud.list_all_patients_including_deleted(db)

    rows = []
    for p in patients:
        row_class = "deleted" if p.deleted_at else ""
        status_badge = (
            '<span class="badge deleted">deleted</span>' if p.deleted_at else '<span class="badge">active</span>'
        )
        rows.append(
            f"""
            <tr class="{row_class}">
              <td>{escape(p.first_name)} {escape(p.last_name)}</td>
              <td>{p.date_of_birth}</td>
              <td>{escape(p.sex.value if hasattr(p.sex, 'value') else str(p.sex))}</td>
              <td>{escape(p.phone_number)}</td>
              <td>{escape(p.city)}, {escape(p.state)} {escape(p.zip_code)}</td>
              <td>{escape(p.preferred_language or "English")}</td>
              <td>{p.created_at.strftime("%Y-%m-%d %H:%M UTC")}</td>
              <td>{status_badge}</td>
              <td><code style="font-size:0.75rem">{p.patient_id}</code></td>
            </tr>
            """
        )

    table_or_empty = (
        f"""
        <table>
          <thead>
            <tr>
              <th>Name</th><th>DOB</th><th>Sex</th><th>Phone</th><th>Address</th>
              <th>Language</th><th>Registered</th><th>Status</th><th>Patient ID</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        """
        if rows
        else '<div class="empty">No patients registered yet. Call the number to register one.</div>'
    )

    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Patient Registration Dashboard</title>
      {_PAGE_STYLE}
    </head>
    <body>
      <h1>Patient Registration Dashboard</h1>
      <div class="sub">{len(patients)} total patient record(s) &middot; live from the same database the voice agent writes to</div>
      {table_or_empty}
      <div class="refresh">Data via <a href="/patients">GET /patients</a>. Reload this page to see new registrations.</div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
