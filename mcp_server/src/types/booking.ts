// Types and Interfaces
export interface Passenger {
  Name: string;
  Seat: string;
}

export interface BaseBooking {
  PK: string;
  SK: string;
  TenantID: string;
  BookingID: string;
  Type: "FLIGHT" | "HOTEL";
  Status: "CONFIRMED" | "PENDING" | "CANCELLED";
  BookingDate: string;
  LoyaltyInfo?: string;
}

export interface FlightBooking extends BaseBooking {
  Type: "FLIGHT";
  FlightNumber: string;
  Class: string;
  DepartureDateTime: string;
  Passengers: Passenger[];
}

export interface HotelBooking extends BaseBooking {
  Type: "HOTEL";
  HotelName: string;
  Location: string;
  CheckInDate: string;
  CheckOutDate: string;
  RoomType: string;
  NumberOfGuests: number;
}

export type Booking = FlightBooking | HotelBooking;
