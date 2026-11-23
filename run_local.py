"""Start the local capstone service without debug mode or the reloader."""

from app import app
import config


if __name__ == "__main__":
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=False,
        use_reloader=False,
        threaded=False,
    )