from waitress import serve
from tiklocal.app import create_app

def main():
    serve(create_app(), host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()
