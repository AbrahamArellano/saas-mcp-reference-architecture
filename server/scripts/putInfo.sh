#!/bin/bash

# Set your AWS region
AWS_REGION="us-east-1"

# Set your DynamoDB table name
TABLE_NAME="TravelBookings"

# Function to add an item to DynamoDB
add_item() {
    aws dynamodb put-item \
        --table-name $TABLE_NAME \
        --item "$1" \
        --region $AWS_REGION
}

# Tenant 1: ABC123
echo "Adding bookings for Tenant ABC123..."

# Flight booking
add_item '{
    "PK": {"S": "TENANT#ABC123"},
    "SK": {"S": "BOOKING#FLIGHT#F12345"},
    "TenantID": {"S": "ABC123"},
    "BookingID": {"S": "F12345"},
    "Type": {"S": "FLIGHT"},
    "Status": {"S": "CONFIRMED"},
    "CustomerName": {"S": "John Doe"},
    "CustomerEmail": {"S": "johndoe@example.com"},
    "BookingDate": {"S": "2025-05-01"},
    "TotalPrice": {"N": "550.00"},
    "Currency": {"S": "USD"},
    "FlightNumber": {"S": "BA456"},
    "Airline": {"S": "British Airways"},
    "DepartureAirport": {"S": "LHR"},
    "ArrivalAirport": {"S": "JFK"},
    "DepartureDateTime": {"S": "2025-06-15T10:00:00Z"},
    "ArrivalDateTime": {"S": "2025-06-15T13:00:00Z"},
    "Passengers": {"L": [
        {"M": {"Name": {"S": "John Doe"}, "Seat": {"S": "12A"}}},
        {"M": {"Name": {"S": "Jane Doe"}, "Seat": {"S": "12B"}}}
    ]}
}'

# Hotel booking
add_item '{
    "PK": {"S": "TENANT#ABC123"},
    "SK": {"S": "BOOKING#HOTEL#H24680"},
    "TenantID": {"S": "ABC123"},
    "BookingID": {"S": "H24680"},
    "Type": {"S": "HOTEL"},
    "Status": {"S": "PENDING"},
    "CustomerName": {"S": "Bob Johnson"},
    "CustomerEmail": {"S": "bobjohnson@example.com"},
    "BookingDate": {"S": "2025-05-10"},
    "TotalPrice": {"N": "1200.00"},
    "Currency": {"S": "USD"},
    "HotelName": {"S": "Beachside Resort"},
    "Location": {"S": "Bali, Indonesia"},
    "CheckInDate": {"S": "2025-08-01"},
    "CheckOutDate": {"S": "2025-08-07"},
    "RoomType": {"S": "Ocean View Suite"},
    "NumberOfGuests": {"N": "3"}
}'

# Tenant 2: XYZ789
echo "Adding bookings for Tenant XYZ789..."

# Hotel booking
add_item '{
    "PK": {"S": "TENANT#XYZ789"},
    "SK": {"S": "BOOKING#HOTEL#H67890"},
    "TenantID": {"S": "XYZ789"},
    "BookingID": {"S": "H67890"},
    "Type": {"S": "HOTEL"},
    "Status": {"S": "CONFIRMED"},
    "CustomerName": {"S": "Alice Smith"},
    "CustomerEmail": {"S": "alicesmith@example.com"},
    "BookingDate": {"S": "2025-05-05"},
    "TotalPrice": {"N": "800.00"},
    "Currency": {"S": "EUR"},
    "HotelName": {"S": "Grand Hotel Paris"},
    "Location": {"S": "Paris, France"},
    "CheckInDate": {"S": "2025-07-20"},
    "CheckOutDate": {"S": "2025-07-25"},
    "RoomType": {"S": "Deluxe Double"},
    "NumberOfGuests": {"N": "2"}
}'

# Flight booking
add_item '{
    "PK": {"S": "TENANT#XYZ789"},
    "SK": {"S": "BOOKING#FLIGHT#F54321"},
    "TenantID": {"S": "XYZ789"},
    "BookingID": {"S": "F54321"},
    "Type": {"S": "FLIGHT"},
    "Status": {"S": "CONFIRMED"},
    "CustomerName": {"S": "Emma Wilson"},
    "CustomerEmail": {"S": "emmawilson@example.com"},
    "BookingDate": {"S": "2025-05-15"},
    "TotalPrice": {"N": "750.00"},
    "Currency": {"S": "USD"},
    "FlightNumber": {"S": "AA789"},
    "Airline": {"S": "American Airlines"},
    "DepartureAirport": {"S": "LAX"},
    "ArrivalAirport": {"S": "ORD"},
    "DepartureDateTime": {"S": "2025-09-01T08:00:00Z"},
    "ArrivalDateTime": {"S": "2025-09-01T14:00:00Z"},
    "Passengers": {"L": [
        {"M": {"Name": {"S": "Emma Wilson"}, "Seat": {"S": "15C"}}}
    ]}
}'

# Tenant 3: DEF456
echo "Adding booking for Tenant DEF456..."

# Flight booking
add_item '{
    "PK": {"S": "TENANT#DEF456"},
    "SK": {"S": "BOOKING#FLIGHT#F98765"},
    "TenantID": {"S": "DEF456"},
    "BookingID": {"S": "F98765"},
    "Type": {"S": "FLIGHT"},
    "Status": {"S": "PENDING"},
    "CustomerName": {"S": "Michael Brown"},
    "CustomerEmail": {"S": "michaelbrown@example.com"},
    "BookingDate": {"S": "2025-05-20"},
    "TotalPrice": {"N": "1200.00"},
    "Currency": {"S": "EUR"},
    "FlightNumber": {"S": "LH456"},
    "Airline": {"S": "Lufthansa"},
    "DepartureAirport": {"S": "FRA"},
    "ArrivalAirport": {"S": "SIN"},
    "DepartureDateTime": {"S": "2025-10-10T22:00:00Z"},
    "ArrivalDateTime": {"S": "2025-10-11T16:00:00Z"},
    "Passengers": {"L": [
        {"M": {"Name": {"S": "Michael Brown"}, "Seat": {"S": "1A"}}},
        {"M": {"Name": {"S": "Sarah Brown"}, "Seat": {"S": "1B"}}}
    ]}
}'

echo "All bookings have been added successfully!"
