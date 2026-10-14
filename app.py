import multiprocessing

from coolmemo_app.server import run


if __name__ == "__main__":
    multiprocessing.freeze_support()
    run()
