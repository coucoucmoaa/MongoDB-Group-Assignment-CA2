##----
# MongoDB.py
# Group 7
# Tiphaine, Lucas and Johan
# Paris City Trash System - wasteReport & recyclingBins

# Console application using PyMongo
##----

##----
# LIB
##----

import os
import re
import json
from datetime import datetime

from bson.objectid import ObjectId
from bson.errors import InvalidId

from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

##----
# CONFIG
##----

DB_NAME = "cityTrashSystem"
DB_HOST = "localhost"
DB_PORT = 27017
DB_USER = "Admin"
DB_PASSWORD = "pa33word"
COLLECTION_NAMES = ["recyclingBins", "wasteReports"]


#---- 
# COLLECTION DEFINITIONS (add / update / display / search)
#   name     : field name (dotted name = embedded document)
#   label    : text shown to the user in prompts
#   type     : str | int | float | bool | list | enum | point
#   required : must be filled in when adding a document
#   editable : can be changed in the Update option
#---- 
COLLECTIONS = {
    "recyclingBins": {
        "id_field": "binId",
        "search_fields": ["binType", "area", "status", "acceptedMaterials"],
        "fields": [
            {"name": "binId", "label": "Bin ID", "type": "int", "required": True, "editable": False},
            {"name": "binType", "label": "Bin type", "type": "str", "required": True, "editable": True},
            {"name": "status", "label": "Status", "type": "str", "required": True, "editable": True},
            {"name": "isOverflow", "label": "Overflowing?", "type": "bool", "required": True, "editable": True},
            {"name": "fillLevel", "label": "Fill level", "type": "float", "required": True, "editable": True,
             "min": 0, "max": 100},
            {"name": "capacity", "label": "Capacity (litres)", "type": "float", "required": True, "editable": True,
             "min": 0},
            {"name": "area", "label": "Area", "type": "str", "required": True, "editable": True},
            {"name": "location", "label": "Location", "type": "point", "required": True, "editable": True},
            {"name": "acceptedMaterials", "label": "Accepted materials (comma-separated)", "type": "list",
             "required": False, "editable": True},
        ],
        "defaults": {
            "lastCollectedAt": lambda: datetime.now(),
            "maintenanceHistory": lambda: [],
        },
    },
    "wasteReports": {
        "id_field": "_id",
        "search_fields": ["description", "wasteType", "area", "category", "reporter.username"],
        "fields": [
            {"name": "category", "label": "Category", "type": "enum", "required": True, "editable": True,
             "choices": ["illegalDumping", "missedCollection", "overflowingBin", "hazardousWaste"]},
            {"name": "wasteType", "label": "Waste type", "type": "str", "required": True, "editable": True},
            {"name": "description", "label": "Description", "type": "str", "required": True, "editable": True},
            {"name": "status", "label": "Status", "type": "str", "required": True, "editable": True},
            {"name": "estimatedWeight", "label": "Estimated weight (kg)", "type": "float", "required": False,
             "editable": True, "min": 0},
            {"name": "area", "label": "Area (e.g. Paris 18e)", "type": "str", "required": True, "editable": True},
            {"name": "binId", "label": "Related bin ID (optional)", "type": "int", "required": False,
             "editable": True},
            {"name": "photos", "label": "Photo URLs (comma-separated)", "type": "list", "required": False,
             "editable": True},
            {"name": "location", "label": "Location", "type": "point", "required": True, "editable": True},
            {"name": "reporter.username", "label": "Reporter username", "type": "str", "required": True,
             "editable": False},
            {"name": "reporter.isVerifiedUser", "label": "Verified user?", "type": "bool", "required": True,
             "editable": False},
        ],
        "defaults": {
            "reportedAt": lambda: datetime.now(),
            "resolvedAt": lambda: None,
        },
    },
}


#---- 
# INPUT HELPERS
#----
def ask_menu_choice(prompt, valid_choices):
    while True:
        choice = input(prompt).strip()
        if choice in valid_choices:
            return choice
        print(f"  Invalid choice. Please enter one of: {', '.join(valid_choices)}")


def ask_yes_no(prompt):
    while True:
        answer = input(f"{prompt} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer y or n.")


def ask_float(prompt, min_value=None, max_value=None):
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
        except ValueError:
            print("  Invalid number, please try again.")
            continue
        if min_value is not None and value < min_value:
            print(f"  Must be at least {min_value}.")
            continue
        if max_value is not None and value > max_value:
            print(f"  Must be at most {max_value}.")
            continue
        return value


def ask_field_value(field):
    label = field["label"]
    required = field["required"]
    ftype = field["type"]
    hint = "" if required else " (optional, Enter to skip)"

    if ftype == "enum":
        choices = field["choices"]
        print(f"{label}{hint}:")
        for i, choice in enumerate(choices, start=1):
            print(f"  {i}. {choice}")
        valid = [str(i) for i in range(1, len(choices) + 1)]
        while True:
            raw = input("Your choice: ").strip()
            if raw == "" and not required:
                return None
            if raw in valid:
                return choices[int(raw) - 1]
            print(f"  Please enter a number between 1 and {len(choices)}.")

    if ftype == "point":
        print(f"{label}:")
        lon = ask_float("  Longitude (e.g. 2.3522): ", -180, 180)
        lat = ask_float("  Latitude (e.g. 48.8566): ", -90, 90)
        return {"type": "Point", "coordinates": [lon, lat]}

    while True:
        raw = input(f"{label}{hint}: ").strip()

        if raw == "":
            if required:
                print("  This field is required.")
                continue
            return None

        try:
            if ftype == "str":
                return raw

            if ftype == "int":
                return int(raw)

            if ftype == "float":
                value = float(raw)
                if "min" in field and value < field["min"]:
                    print(f"  Must be at least {field['min']}.")
                    continue
                if "max" in field and value > field["max"]:
                    print(f"  Must be at most {field['max']}.")
                    continue
                return value

            if ftype == "bool":
                if raw.lower() in ("y", "yes", "true"):
                    return True
                if raw.lower() in ("n", "no", "false"):
                    return False
                print("  Please answer y or n.")
                continue

            if ftype == "list":
                return [item.strip() for item in raw.split(",") if item.strip()]

        except ValueError:
            print("  Invalid number, please try again.")

##----
# DATABASE CONNECTION
##----
def connect_db():
    uri = (
        f"mongodb://{(DB_USER)}:{(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/?authSource={DB_NAME}"
    )
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print(f"Connected to database '{DB_NAME}'.")
        return client[DB_NAME]
    except (ConnectionFailure, ServerSelectionTimeoutError):
        print("Error: could not connect to MongoDB. Is the server running?")
    return None


#---- 
# MENUS
#---- 
def choose_collection():
    print("\n===== CITY TRASH SYSTEM =====")
    print("Select a collection:")
    for i, name in enumerate(COLLECTION_NAMES, start=1):
        print(f"  {i}. {name}")
    print(f"  {len(COLLECTION_NAMES) + 1}. Exit")
    valid = [str(i) for i in range(1, len(COLLECTION_NAMES) + 2)]
    choice = int(ask_menu_choice("Your choice: ", valid))
    if choice == len(COLLECTION_NAMES) + 1:
        return None
    return COLLECTION_NAMES[choice - 1]


def show_action_menu(collection_name):
    print(f"\n----- {collection_name} -----")
    print("  1. Display all documents")
    print("  2. Add a new document")
    print("  3. Update a document")
    print("  4. Delete a document")
    print("  5. Search documents")
    print("  6. Exit System")
    print("  0. Back to collection menu")
    return ask_menu_choice("Your choice: ", ["0", "1", "2", "3", "4", "5", "6"])


#---- 
# ACTIONS
#---- 
def display_all(col, name):
    docs = list(col.find())

    if not docs:
        print("No Document has been find in '{name}'.")
        return
    
    print("All Documents in '{name}'.")
    i = 1
    for doc in docs:
        print(f"\n\ndocument n{i}:\n")
        print(doc)
        i += 1
    i = 1
    print(f"\n{len(docs)} Documents found.")


def add_document(col, name):
    raw = input("write your Document:\n")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        print("Invalid JSON, please try again.")
        return
    col.insert_one(doc)

def find_document(col, name):
    id_field = COLLECTIONS[name]["id_field"]
    raw = input(f"Enter the {id_field} of the document: ").strip()

    try:
        key = ObjectId(raw) if id_field == "_id" else int(raw)
    except (InvalidId, ValueError):
        print("Invalid ID format.")
        return None

    doc = col.find_one({id_field: key})
    if doc is None:
        print("Document not found.")
    return doc

def update_document(col, name):
    definition = COLLECTIONS[name]
    id_field = definition["id_field"]

    doc = find_document(col, name)
    if doc is None:
        return
    print("\nCurrent values:")
    print(doc) 
    editable = [f for f in definition["fields"] if f["editable"]]
    print("\nWhich field do you want to change?")
    for i, field in enumerate(editable, start=1):
        print(f"  {i}. {field['label']}")
    print("  0. Cancel")
    choice = ask_menu_choice("Your choice: ", [str(i) for i in range(len(editable) + 1)])
    if choice == "0":
        return
    field = editable[int(choice) - 1]

    new_value = ask_field_value(field)
    if new_value is None:
        print("No change made.")
        return
    changes = {field["name"]: new_value}

    if name == "wasteReports" and field["name"] == "status" and new_value == "resolved":
        changes["resolvedAt"] = datetime.now()

    try:
        result = col.update_one({id_field: doc[id_field]}, {"$set": changes})
        print(f"Matched: {result.matched_count}, modified: {result.modified_count}.")
    except WriteError as e:
        print(f"Error: the update failed validation ({e}).")

def delete_document(col, name):
    definition = COLLECTIONS[name]
    id_field = definition["id_field"]

    doc = find_document(col, name)
    if doc is None:
        return
    print("\nCurrent values:")
    print(doc)
    resp = ask_yes_no("do you want to delete this document ?")
    if resp is True:
        col.delete_one(doc)
        print("document deleted.")
    else:
        return


def search_documents(col, name):
    search_fields = COLLECTIONS[name]["search_fields"]

    keyword = input("Enter a keyword to search for: ").strip()
    if keyword == "":
        print("Search cancelled: no keyword entered.")
        return

    pattern = re.escape(keyword)
    query = {"$or": [
        {field: {"$regex": pattern, "$options": "i"}}
        for field in search_fields
    ]}

    docs = list(col.find(query))

    if not docs:
        print(f"No documents found matching '{keyword}'.")
        return

    print(f"\n--- Search results for '{keyword}' in {name} ---")
    for doc in docs:
        print(doc)
    print(f"\n{len(docs)} document(s) found.")


ACTIONS = {
    "1": display_all,
    "2": add_document,
    "3": update_document,
    "4": delete_document,
    "5": search_documents,
}


#---- 
# MAIN LOOP
#---- 
def run_collection_session(db, collection_name):
    col = db[collection_name]
    while True:
        choice = show_action_menu(collection_name)
        if choice == "6":
            return False
        if choice == "0":
            return True
        try:
            ACTIONS[choice](col, collection_name)
        except PyMongoError as e:
            print(f"Database error: {e}")


def main():
    db = connect_db()
    if db is None:
        return
    while True:
        collection_name = choose_collection()
        if collection_name is None:
            break
        if not run_collection_session(db, collection_name):
            break
    print("\nGoodbye!")


if __name__ == "__main__":
    main()