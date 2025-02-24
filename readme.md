<p align="center">
  <h1 align="center"><code>macos-grok-overlay</code></h1>
</p>

<p align="center">
A simple macOS overlay application for pinning <code>grok.com</code> to a dedicated window and key command <code>option+space</code>.
</p>


## INSTALLATION:

  Install the latest stable release with:

```bash
python3 -m pip install macos-grok-overlay
```

  Once you've installed the package, you can enable it to be automatically launched at startup with:

```bash
python3 -m macos-grok-overlay --install-startup
```

## USAGE:

  Once the application is launched, it should immediately open a window dedicated to `grok.com`. Pressing `Option + Space` while the window is open will hide it, and pressing it again at any point will reveal it and pin it as the top-most window overlay on top of other applications. This enables quick and easy access to Grok on macOS.


## HOW IT WORKS:

  This is a very thin `pyobjc` application written to contain a web view of the current production Grok website. Most of the logic contained in this small application is for stylistic purposes, making the overlay shaped correctly, resizeable, draggable, and able to be summoned anywhere easily with a single keyboard command.

## MISC:

  This was a small personal weekend project, and is not a product of the xAI team nor is it formally affiliated with them. Please file issues and I'll be happy to adjust, but I also highly recommend you look at the source code yourself if you want to change something. It's a very small and simple project entirely in [__main__.py](/macos-grok-overlay/__main__.py), Grok (or similar) could easily help you modify it for your own purposes.
