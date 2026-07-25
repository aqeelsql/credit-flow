try:
    from app.celery_app import celery_app
except ModuleNotFoundError:
    celery_app = None

from app.due_scanner import scan_due_posts as run_due_post_scan


if celery_app is not None:
    scan_due_posts = celery_app.task(name="scheduler.scan_due_posts")(run_due_post_scan)
else:
    scan_due_posts = run_due_post_scan
