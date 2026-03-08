import apprise
from app.settings import settings

notifications = apprise.Apprise()
if settings.notification_url:
    notifications.add(settings.notification_url)


def send_search_notification(body: str, level: apprise.NotifyType):
    return notifications.notify(title="Search Job", body=body, notify_type=level)
