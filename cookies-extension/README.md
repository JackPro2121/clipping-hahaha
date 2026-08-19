# YouTube Cookies Exporter (Brave / Chrome)

Ye extension YouTube ke login cookies ko `cookies.txt` format me export karta hai,
taake GitHub Actions pe chalne wala yt-dlp YouTube ka bot-check bypass kar sake.

## Install karo (Brave)

1. Brave kholo aur address bar me jaao: `brave://extensions`
2. Top-right me **Developer mode** ON karo
3. **Load unpacked** button dabao
4. Is folder ko select karo: `cookies-extension` (jo folder is file ke andar hai)
5. Extension install ho jayega

## Export karo

1. Naye tab me `https://www.youtube.com` kholo aur **login** raho (ye zaroori hai)
2. Toolbar me extension icon pe click karo
3. **Export cookies.txt** dabao
4. File save ho jayegi (`youtube_cookies.txt`)

## Use karo

Export ki hui file ka path mujhe (opencode) ko batao — mai base64 encode karke
`YT_COOKIES` secret set kar dunga. Phir pipeline YouTube download kar sakegi.

## Notes

- Cookies me tumhara YouTube login token hota hai — ye file kahin share mat karna
- Jab tak YouTube pe login raho, cookies kaam karti rahengi (usually months tak)
- Logout/login change ho jaye to dobara export karna
- Extension apne project folder me hai — isme koi secret nahi hota, sirf export tool hai