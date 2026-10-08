import asyncio
from aiohttp import web
from .config import Config
from .server import create_app


async def serve(config):
    runner = web.AppRunner(create_app(config), access_log=None)
    await runner.setup()
    try:
        site = web.TCPSite(runner, config.host, config.port)
        await site.start()
        host = f"[{config.host}]" if ":" in config.host else config.host
        print(f"LUMINA is ready at http://{host}:{config.port}", flush=True)
        print(f"Filesystem root: {config.root}\nProvider: {config.provider}. No paid fallback.", flush=True)
        await asyncio.Event().wait()
    except OSError as exc:
        if exc.errno in (48, 98, 10048) or getattr(exc, "winerror", None) == 10048:
            print(f"Port {config.port} is occupied. Another LUMINA instance may already be running. Change LUMINA_PORT or port in lumina.toml.")
        else:
            print(f"LUMINA could not listen on port {config.port}. Check the host and port settings.")
    finally:
        await runner.cleanup()


def main():
    try:
        config = Config.load()
        asyncio.run(serve(config))
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        print(f"LUMINA configuration error: {exc}")
    except KeyboardInterrupt:
        print("LUMINA stopped.")


if __name__ == "__main__":
    main()

