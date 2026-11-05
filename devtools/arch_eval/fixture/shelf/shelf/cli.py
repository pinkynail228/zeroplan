"""Command line: add, list, done, queue."""
import argparse

from . import store


def line(book):
    mark = "x" if book["read"] else " "
    author = " — " + book["author"] if book["author"] else ""
    return "%d [%s] %s%s" % (book["id"], mark, book["title"], author)


def main(argv):
    parser = argparse.ArgumentParser(prog="shelf")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("title")
    add.add_argument("--author", default="")
    sub.add_parser("list")
    done = sub.add_parser("done")
    done.add_argument("id", type=int)
    sub.add_parser("queue")
    args = parser.parse_args(argv)
    if args.command == "add":
        print(line(store.add(args.title, args.author)))
    elif args.command == "list":
        for book in store.load():
            print(line(book))
    elif args.command == "done":
        try:
            print(line(store.mark_read(args.id)))
        except KeyError:
            print("no book %d" % args.id)
            return 1
    elif args.command == "queue":
        for book in store.load():
            if not book["read"]:
                print(line(book))
    return 0
