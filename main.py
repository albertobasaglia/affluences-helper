import requests
import re

favorite_spots = [11, 46, 47, 13, 23, 25, 35, 48, 58, 9, 7, 5, 12, 10, 8, 6, 15, 17, 19, 21, 27, 29, 31, 33, 44, 42, 50, 52, 54, 56] # Thanks for everything you've done, my favorite spots :)
email = "<EMAIL GOES HERE>" # Affluences email
date = "2024-11-20"
start_hour = "08:30"
duration = 9 * 30
pattern = "Posto a sedere ([0-9]+)" # Seat nomenclature pattern
structure_id = "60f4531d-c564-4603-bb04-b909629653de" # unipd Someda structure id


class Place:
    def __init__(self, number, availability, resid):
        self.number = number
        self.availability = availability
        self.resid = resid

    def __repr__(self):
        return "{}: {}".format(self.number, self.availability)


def watch_to_minutes(watch: str) -> int:
    parts = watch.split(":")
    return int(parts[0])*60 + int(parts[1])


def minutes_to_watch(minutes: int) -> str:
    return "{:02}:{:02}".format(int(minutes/60), minutes % 60)



availability_url = f"https://reservation.affluences.com/api/resources/{structure_id}/available"

granularity = 30
maxres = 30 * 8

places = []

def get_available(params, places):
    res = requests.get(availability_url, params=params)
    resources = res.json()


    for resource in resources:
        m = re.match(pattern, resource["resource_name"])
        if m == None:
            continue

        identifier = int(m.group(1))
        resid = int(resource["resource_id"])

        availability = set()
        place = Place(identifier, availability, resid)

        found = False
        for p in places:
            if p.resid == resid:
                place = p
                found = True
                break

        for slot in resource["hours"]:
            if slot["places_bookable"] != 1:
                continue
            hour = slot["hour"]
            availability.add(hour)

        if not found:
            places.append(place)

counter = 0
while counter < duration:
    st = minutes_to_watch(watch_to_minutes(start_hour) + counter)
    params = {
        "type": 972,
        "capacity": 1,
        "date": date,
        "duration": min(maxres, duration-counter),
        "start_hour": st
    }
    print("get_available: {}".format(params))
    get_available(params, places)
    counter += min(maxres, duration-counter)

must_contain = set()
start_minutes = watch_to_minutes(start_hour)
counter = 0
while counter < duration:
    must_contain.add(minutes_to_watch(start_minutes + counter))
    counter += granularity

complete_places = []

complete_places = list(filter(lambda place: place.availability.issuperset(must_contain), places))

for place in complete_places:
    print("Complete {}".format(place))


def reserve_place(resid, date, start_time, end_time):
    print("reserve_place: {}, {}, {} -> {}".format(resid, date, start_time, end_time))
    body = {
        "auth_type": None,
        "email": email,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "note": None,
        "user_firstname": None,
        "user_lastname": None,
        "user_phone": None,
        "person_count": 1
    }
    res = requests.post("https://reservation.affluences.com/api/reserve/{}".format(resid),body)
    if res.status_code != 200:
        print(res.text)
    print(res)


def make_reservation(place):
    print("Reserving place: {}".format(place.number))
    counter = 0
    while counter < duration:
        st = minutes_to_watch(watch_to_minutes(start_hour) + counter)
        d = min(maxres, duration-counter)
        en = minutes_to_watch(watch_to_minutes(st) + d)
        reserve_place(place.resid, date, st, en)
        counter += d

for favid in favorite_spots:
    for place in complete_places:
        if place.number == favid:
            make_reservation(place)
            exit(0)

print("Falling back")

make_reservation(places[0])
