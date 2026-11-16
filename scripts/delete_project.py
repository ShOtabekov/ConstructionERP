"""Delete a construction project with ALL its data (test cleanup).

Run with Odoo shell. Dry run by default - only prints what would be deleted:

    Get-Content scripts\\delete_project.py | .\\.venv\\Scripts\\python.exe .\\odoo\\odoo-bin shell -c .\\config\\odoo.conf -d DB

To really delete, set APPLY=1 (PowerShell):  $env:APPLY="1"
Project code via PROJECT_CODE (default SOMON-001).
Clients (contacts) are NOT deleted.
"""
import os

CODE = os.environ.get("PROJECT_CODE", "SOMON-001")
APPLY = os.environ.get("APPLY") == "1"
cr = env.cr


def ids(sql, params):
    cr.execute(sql, params)
    return tuple(r[0] for r in cr.fetchall()) or (0,)


def table_exists(name):
    cr.execute("SELECT to_regclass(%s)", [name])
    return cr.fetchone()[0] is not None


cr.execute("SELECT id, name FROM construction_project WHERE code = %s", [CODE])
row = cr.fetchone()
if not row:
    print("Project with code %s not found." % CODE)
else:
    project_id, name = row
    pname = name.get("ru_RU") or name.get("en_US") if isinstance(name, dict) else name
    buildings = ids("SELECT id FROM construction_building WHERE project_id=%s", [project_id])
    entrances = ids("SELECT id FROM construction_entrance WHERE building_id IN %s", [buildings])
    floors = ids("SELECT id FROM construction_floor WHERE entrance_id IN %s", [entrances])
    apartments = ids(
        "SELECT id FROM construction_apartment WHERE floor_id IN %s", [floors])
    reservations = ids(
        "SELECT id FROM construction_reservation WHERE apartment_id IN %s", [apartments]
    ) if table_exists("construction_reservation") else (0,)
    contracts = ids(
        "SELECT id FROM construction_contract WHERE apartment_id IN %s", [apartments]
    ) if table_exists("construction_contract") else (0,)
    plans = ids(
        "SELECT id FROM construction_payment_plan WHERE contract_id IN %s", [contracts]
    ) if table_exists("construction_payment_plan") else (0,)
    schedules = ids(
        "SELECT id FROM construction_payment_schedule WHERE plan_id IN %s", [plans]
    ) if table_exists("construction_payment_schedule") else (0,)
    payments = ids(
        "SELECT id FROM construction_payment WHERE schedule_id IN %s", [schedules]
    ) if table_exists("construction_payment") else (0,)

    def n(t):
        return 0 if t == (0,) else len(t)

    print("=" * 60)
    print("Project: %s (%s)" % (pname, CODE))
    for label, t in [
        ("blocks", buildings), ("entrances", entrances), ("floors", floors),
        ("units", apartments), ("reservations", reservations),
        ("contracts", contracts), ("payment plans", plans),
        ("schedule lines", schedules), ("payments", payments),
    ]:
        print("  %-15s %s" % (label, n(t)))
    print("=" * 60)

    if not APPLY:
        print("DRY RUN - nothing deleted. Set APPLY=1 to delete.")
    else:
        models = {
            "construction.payment": payments,
            "construction.payment.schedule": schedules,
            "construction.payment.plan": plans,
            "construction.contract": contracts,
            "construction.reservation": reservations,
            "construction.apartment": apartments,
            "construction.floor": floors,
            "construction.entrance": entrances,
            "construction.building": buildings,
            "construction.project": (project_id,),
        }
        for model, rec_ids in models.items():
            if rec_ids == (0,):
                continue
            cr.execute("DELETE FROM mail_message WHERE model=%s AND res_id IN %s", [model, rec_ids])
            cr.execute("DELETE FROM mail_followers WHERE res_model=%s AND res_id IN %s", [model, rec_ids])
            cr.execute("DELETE FROM mail_activity WHERE res_model=%s AND res_id IN %s", [model, rec_ids])
            cr.execute("DELETE FROM ir_attachment WHERE res_model=%s AND res_id IN %s", [model, rec_ids])
        if contracts != (0,):
            cr.execute("UPDATE construction_contract SET reservation_id=NULL WHERE id IN %s", [contracts])
        if reservations != (0,):
            cr.execute("UPDATE construction_reservation SET contract_id=NULL WHERE id IN %s", [reservations])
        for table, rec_ids in [
            ("construction_payment", payments),
            ("construction_payment_schedule", schedules),
            ("construction_payment_plan", plans),
            ("construction_contract", contracts),
            ("construction_reservation", reservations),
            ("construction_apartment", apartments),
            ("construction_floor", floors),
            ("construction_entrance", entrances),
            ("construction_building", buildings),
        ]:
            if rec_ids != (0,):
                cr.execute("DELETE FROM %s WHERE id IN %%s" % table, [rec_ids])
        cr.execute("DELETE FROM construction_project WHERE id=%s", [project_id])
        cr.commit()
        env.invalidate_all()
        print("DELETED.")
