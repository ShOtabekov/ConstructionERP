"""Move the USD/TJS rate from each apartment to its project.

Before 19.0.1.4.0 every apartment had its own manually entered rate.
Now the rate lives on the project and apartments take it from there.
Copy the most recent apartment rate to the project BEFORE the ORM turns
the apartment column into a related field and recomputes it.
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        ALTER TABLE construction_project
        ADD COLUMN IF NOT EXISTS usd_tjs_rate numeric
    """)
    cr.execute("""
        UPDATE construction_project p
           SET usd_tjs_rate = sub.rate
          FROM (
                SELECT DISTINCT ON (project_id)
                       project_id, usd_tjs_rate AS rate
                  FROM construction_apartment
                 WHERE usd_tjs_rate > 0 AND project_id IS NOT NULL
              ORDER BY project_id, write_date DESC NULLS LAST, id DESC
               ) sub
         WHERE sub.project_id = p.id
           AND COALESCE(p.usd_tjs_rate, 0) = 0
    """)
