# Main file for app

import os
import time
import calendar
import datetime
from datetime import date

current = str(date.today())
print(current) # yyyy-mm-day

#def main():
    #"""Figure out the tasks that need to be done immediately (Within the next week or day)"""

def current_calendar():
    text_calendar = calendar.TextCalendar()
    text_calendar.formatyear(2026)
    text_calendar.pryear(2026)
current_calendar()

class Task:
    def __init__(self, name: type = str, date: type = str, desc: type = str, location: type = str, host: type = str, tags: type = list):
        self.task_name = name
        self.task_date = date
        self.task_host = host
        self.task_desc = desc
        self.task_location = location
        self.task_tags = tags

        self.task_importance: type = int

        pass

    def time_til(self, current):
        #Returns the time until this task
        pass

    def has_tag(self, tag):
        for i in self.task_tags:
            if i == tag:
                return True
        return False

    def get_importance(self, user):
        importance = -1
        with open ("host.txt") as file: #
            file.readline()
            for i in file.readlines():
                entry = i.split(",")
                if entry[0] == self.task_host:
                    if user == (self.task_host):
                        importance = int(entry[1].strip())
                    pass

        return importance
    pass

hackathon = Task("Hackathon", "2026-11-13", "BITHCH", "McNair Hall", "COE", ["compsci", "robotics", "nerd", "programming"])

#def sort(list):
    #for item in list: # sort by tag, importance and alphabetically, integrate get_importance

#def notify():
    #"""Send colorful notifications to users based on new events in NCAT colors"""

#def register():
    # Allow users to register. Guest by default. Whenever an account is created the username and corresponding password is saved to a text file. There is also version control for an admin which has additonal privleges like visualizing accounts, changing passwords, and deleting accounts

#def search(query):
    #"""Search for events based on name (Substring or exact) and tags (from Task class)"""
    #if query:
        # Additional logic goes here for tag in tags list to search for

#def deadline(current, date):
    #Current is today, date is the date of any event on the calendar. If the even is within a week, the circle on each date on the calendar turns red and becomes a notification (notify) otherwise, it just stores the value of the difference between date and current

def today(current):
    """Get the current day as an integer from the date"""
    new_current = int(current[8:])
    return new_current
today(current)
