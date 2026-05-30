# Font Awesome (local)

The UI loads [Font Awesome Free 7.2.0](https://fontawesome.com/) from a local web
package (not npm).

Create the vendor symlink (adjust the source path if your install lives elsewhere):

```bash
ln -sfn /Users/tal/Fonts/fontawesome-free-7.2.0-web web/vendor/fontawesome-free-7.2.0-web
```

Override the directory for Vite with `FONTAWESOME_WEB` if needed.
