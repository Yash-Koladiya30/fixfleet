import instaloader
from instaloader import Profile, Instaloader
import json


def fetch_instagram_data(username):
    L = Instaloader()

    # Login required for follower/followee lists on most accounts.
    # L.login('your_username', 'your_password')

    profile = Profile.from_username(L.context, username)

    followers = []
    for follower in profile.get_followers():
        followers.append({
            'username': follower.username,
            'name': follower.full_name,
            'bio': follower.biography,
            'profile_pic': follower.profile_pic_url,
            'followers': follower.followers,
            'following': follower.followees,
        })

    following = []
    for followee in profile.get_followees():
        following.append({
            'username': followee.username,
            'name': followee.full_name,
            'bio': followee.biography,
            'profile_pic': followee.profile_pic_url,
            'followers': followee.followers,
            'following': followee.followees,
        })

    data = {
        'username': username,
        'followers': followers,
        'following': following,
    }
    return json.dumps(data, indent=4)


if __name__ == '__main__':
    username = input("Enter the Instagram username: ")
    print(fetch_instagram_data(username))
