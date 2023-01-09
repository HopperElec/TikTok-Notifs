from os.path import isfile
from json import load as json_load, dump as json_write
from requests import get
from time import sleep
import asyncio as aio
# noinspection PyProtectedMember
from playwright._impl._api_types import TimeoutError
from tiktokapipy import TikTokAPIError
from tiktokapipy.async_api import AsyncTikTokAPI
from tiktokapipy.models.video import video_link
from windows_toasts import WindowsToaster, ToastText1
from webbrowser import open as web_open

TOASTER = WindowsToaster('TikTok notifications')


def get_following(session_id):
    print("Getting following list")
    return get(
        "https://www.tiktok.com/api/user/list",
        {"count": 10000, "minCursor": 0},
        cookies={"sessionid": session_id}
    ).json()['userList']


class Progressor:
    DEFAULT_CONCURRENT_USERS = 1
    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_SHOW_TOAST = False
    DEFAULT_PRINT_PROGRESS = True

    def __init__(self, known_videos, users, concurrent_users=DEFAULT_CONCURRENT_USERS, **kwargs):
        self.known_videos = known_videos
        self.users_loaded = 0
        self.total_users = len(users)
        self.user_sem = aio.Semaphore(concurrent_users)
        aio.run(self.fetch_new_from_users(users, **kwargs))

    async def fetch_user(self, user, api, retry_attempts=DEFAULT_RETRY_ATTEMPTS, print_progress=DEFAULT_PRINT_PROGRESS):
        unique_id = user['user']['uniqueId']
        async with self.user_sem:
            if print_progress:
                print(f"{self.users_loaded}/{self.total_users} | Fetching user {unique_id}")
            for _ in range(retry_attempts):
                try:
                    return await api.user(user['user']['id'])
                except TikTokAPIError as e:
                    print(e)
                except TimeoutError:
                    pass
        if unique_id not in self.known_videos:
            self.known_videos[unique_id] = []
        self.users_loaded += 1
        if print_progress:
            print(f"Failed to fetch user {unique_id} after {retry_attempts} retries")
        return None

    # Returns new videos from the given user
    def get_new_from_user(self, user):
        # noinspection PyProtectedMember
        for video in user.videos._light_models:
            if video.id in self.known_videos[user.unique_id]:
                return
            self.known_videos[user.unique_id].append(video.id)
            yield video_link(video.id)

    # Gets and shows new videos from the given user
    async def show_new_from_user(self, user, print_progress=DEFAULT_PRINT_PROGRESS, show_toast=DEFAULT_SHOW_TOAST):
        if print_progress:
            print("Searching for new videos from", user.unique_id)
        for video_url in self.get_new_from_user(user):
            if print_progress:
                print(video_url)
            if show_toast:
                toast = ToastText1()
                toast.SetBody("New TikTok by "+user.unique_id)
                toast.on_activated = lambda _: web_open(video_url, 2)
                TOASTER.show_toast(toast)

    # Fetches users then gets and shows new videos from them
    async def fetch_new_from_users(self, users, **kwargs):
        async with AsyncTikTokAPI() as api:
            for user in aio.as_completed([self.fetch_user(user, api, **kwargs) for user in users]):
                await self.show_new_from_user(await user, **kwargs)


def get_known_videos(known_videos_filename):
    if isfile(known_videos_filename):
        with open(known_videos_filename) as json_file:
            return json_load(json_file)
    return {}


def loop(users, known_videos_filename="known_videos.json", delay=3600, **kwargs):
    known_videos = get_known_videos(known_videos_filename)
    while True:
        known_videos = Progressor(known_videos, users, **kwargs).known_videos
        with open(known_videos_filename, "w") as json_file:
            json_write(known_videos, json_file)
        sleep(delay)


if __name__ == "__main__":
    if isfile("sessionid"):
        with open("sessionid") as sessionid_file:
            sessionid = sessionid_file.read()
    else:
        sessionid = input("Paste your TikTok session ID: ")
    following = get_following(sessionid)
    loop(following)
