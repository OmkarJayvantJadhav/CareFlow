"""The fictional hospital: departments, doctors and demo accounts. All names are invented."""

from datetime import time

HOSPITAL = "Indravani General Hospital"

# name, floor, OPD start, OPD end
DEPARTMENTS = [
    ("General Medicine", 1, time(9, 0), time(14, 0)),
    ("Cardiology", 3, time(9, 0), time(13, 0)),
    ("ENT", 2, time(9, 0), time(13, 0)),
    ("Orthopaedics", 2, time(9, 30), time(13, 30)),
    ("Paediatrics", 1, time(10, 0), time(14, 0)),
    ("Dermatology", 4, time(9, 0), time(13, 0)),
    ("Gynaecology", 3, time(9, 30), time(13, 30)),
    ("Ophthalmology", 4, time(9, 0), time(13, 0)),
]

MON, TUE, WED, THU, FRI, SAT = 1, 2, 3, 4, 5, 6

# name, department, languages, ISO OPD weekdays, slot minutes
DOCTORS = [
    ("Dr. Suresh Pawar", "General Medicine", ["mr", "hi", "en"], [MON, TUE, WED, THU, FRI, SAT], 10),
    ("Dr. Kavita Joshi", "General Medicine", ["en", "hi", "mr"], [MON, TUE, WED, THU, FRI], 10),
    ("Dr. Imran Shaikh", "General Medicine", ["hi", "en"], [TUE, THU, SAT], 10),
    ("Dr. Anand Kulkarni", "Cardiology", ["mr", "hi", "en"], [MON, WED, SAT], 15),
    ("Dr. Farah Siddiqui", "Cardiology", ["en", "hi"], [TUE, THU, FRI], 15),
    ("Dr. Meera Iyer", "Cardiology", ["en"], [MON, THU, SAT], 20),
    ("Dr. Snehal Gokhale", "ENT", ["mr", "en"], [MON, WED, FRI], 15),
    ("Dr. Rohit Malhotra", "ENT", ["hi", "en"], [TUE, THU, SAT], 15),
    ("Dr. Vikram Bhosale", "Orthopaedics", ["mr", "hi", "en"], [MON, WED, FRI, SAT], 15),
    ("Dr. Neha Kapoor", "Orthopaedics", ["en", "hi"], [TUE, THU], 15),
    ("Dr. Aparna Deshpande", "Paediatrics", ["mr", "en"], [MON, TUE, WED, THU, FRI], 15),
    ("Dr. Joseph Mathew", "Paediatrics", ["en"], [TUE, THU, SAT], 15),
    ("Dr. Ritu Agarwal", "Dermatology", ["hi", "en"], [MON, WED, FRI], 15),
    ("Dr. Prakash Shinde", "Dermatology", ["mr", "hi"], [TUE, SAT], 15),
    ("Dr. Sunita Patwardhan", "Gynaecology", ["mr", "en", "hi"], [MON, TUE, THU, FRI], 20),
    ("Dr. Ayesha Khan", "Gynaecology", ["hi", "en"], [WED, SAT], 20),
    ("Dr. Nitin Chavan", "Ophthalmology", ["mr", "hi", "en"], [MON, WED, FRI], 10),
    ("Dr. Lakshmi Rao", "Ophthalmology", ["en"], [TUE, THU, SAT], 10),
]

# Seeded so that demo flows have predictable starting points. The doctor below is
# fully booked on their next two OPD days, so the waiting list can be demonstrated.
FULLY_BOOKED_DOCTOR = "Dr. Ritu Agarwal"

# Demo patients: name, birth year, language, 10-digit phone (stored masked only).
DEMO_PATIENTS = {
    "asha": ("Asha Patil", 1992, "mr", "9822011234"),
    "vinayak": ("Vinayak Deshmukh", 1958, "mr", "9850044321"),
}

# username, display name, role, demo patient key (patients only)
DEMO_USERS = [
    ("asha", "Asha Patil", "patient", "asha"),
    ("rajan", "Rajan Deshmukh", "caregiver", None),
    ("sunil", "Sunil More", "caregiver", None),
    ("priya", "Priya Nair (reception)", "staff", None),
    ("mehta", "Dr. Mehta (OPD admin)", "admin", None),
    ("sim-desk", "Simulator front desk", "staff", None),
]

# caregiver username, patient key, verified
CAREGIVER_LINKS = [
    ("rajan", "vinayak", True),
    # Sunil's link was never verified, so he must be refused (US-10, TC-08).
    ("sunil", "vinayak", False),
]

FIRST_NAMES = [
    "Aarav", "Aditi", "Ajay", "Akash", "Amol", "Ananya", "Anil", "Anjali", "Arjun", "Ashwini", "Bhavna",
    "Chetan", "Deepa", "Dinesh", "Gauri", "Geeta", "Harish", "Ishaan", "Jyoti", "Kiran", "Komal", "Lata",
    "Mahesh", "Manisha", "Mohan", "Nandini", "Nilesh", "Pooja", "Pradeep", "Prakash", "Rahul", "Rekha",
    "Rohini", "Sachin", "Sakshi", "Sandeep", "Sanjay", "Seema", "Shilpa", "Shreya", "Smita", "Sneha",
    "Sunita", "Swati", "Tanvi", "Tushar", "Uday", "Ujwala", "Varsha", "Vijay", "Vishal", "Yash", "Zoya",
    "Farhan", "Nasreen", "Salim", "Tabassum", "Peter", "Mary", "Thomas", "Gurpreet", "Harpreet",
]  # fmt: skip

LAST_NAMES = [
    "Patil", "Deshmukh", "Jadhav", "Pawar", "Shinde", "Kale", "Gaikwad", "More", "Chavan", "Joshi",
    "Kulkarni", "Deshpande", "Sharma", "Verma", "Gupta", "Yadav", "Singh", "Mishra", "Pandey", "Tiwari",
    "Iyer", "Nair", "Menon", "Pillai", "Reddy", "Rao", "Shaikh", "Khan", "Ansari", "Fernandes",
    "D'Souza", "Gill", "Sandhu", "Bhosale", "Salunkhe", "Wagh", "Thakur", "Mehta", "Shah", "Desai",
]  # fmt: skip
