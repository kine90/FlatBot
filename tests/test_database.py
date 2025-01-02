# test.py
from modules.Database import ExposeDB


def main():
    print("Testing Database Utilities...")
    db_instance = ExposeDB()

    # Print all exposes
    db_instance.print_all_exposes()

    # Clear all exposes
    db_instance.clear_all_exposes()

    # Delete a specific expose
    #delete_expose_by_id("155920388")

if __name__ == "__main__":
    main()