import apprise
from app.settings import settings

notifications = apprise.Apprise()
if settings.notification_url:
    notifications.add(str(settings.notification_url))


def send_sync_notification(body: str):
    return notifications.notify(title="Sync Job", body=body)


def send_search_notification(body: str):
    return notifications.notify(title="Search Job", body=body)
