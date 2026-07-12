[app]

title = Green Impact
package.name = greenimpact
package.domain = org.gamefication

version = 0.3

icon.filename = assets/app_icon.png

source.dir = .
source.include_exts = py,png,jpg,json,txt,md,ico,icns
source.exclude_dirs = tests,bin,dist,__pycache__,.venv,venv

entrypoint = main.py
requirements = python3,kivy,websockets

orientation = landscape
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE
android.api = 35
android.minapi = 26
android.ndk = 28c
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
