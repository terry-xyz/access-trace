import argparse

from .server import create_server


def main():
    parser = argparse.ArgumentParser(description="Serve AccessTrace and its local assessment API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--run-directory", default=".access-trace/runs")
    arguments = parser.parse_args()

    server = create_server(arguments.host, arguments.port, arguments.run_directory)
    print("AccessTrace listening at http://{0}:{1}".format(arguments.host, server.server_port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
