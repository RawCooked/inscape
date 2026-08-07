import instaloader
import browser_cookie3

L = instaloader.Instaloader()

cookies = browser_cookie3.chrome()

session_found = False

for cookie in cookies:
    if cookie.name == "sessionid":
        L.context._session.cookies.set(
            cookie.name,
            cookie.value,
            domain=".instagram.com"
        )
        session_found = True

print("Session found:", session_found)
print("Logged in:", L.context.is_logged_in)
print("User:", L.context.username)