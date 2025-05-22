import { Faker, faker } from "@faker-js/faker";
import { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { getDynamoDbClient, TABLE_NAME } from "../services/dynamoDb";
import { PutCommand } from "@aws-sdk/lib-dynamodb";
import { FlightBooking, Passenger } from "../types/booking";
import httpContext from "express-http-context";

export interface FlightInfo {
  departure: Date;
  arrival: Date;
  origin: string;
  destination: string;
  distance: number;
  duration: number;
  stops: number;
  flightNumber: string;
  airline: string;
  availableSeats: {
    flightClass: string;
    count: number;
    price: number;
  }[];
  frequentFlyerInfo: {
    programName: string;
    milesEarned: number;
    tierPointsEarned: number;
  };
}

const AIRLINES = ["Delta", "United", "American", "Southwest"];
const FLIGHT_CLASSES = ["Economy", "Business", "First"];
const FREQUENT_FLYER_PROGRAMS = {
  Delta: "SkyMiles",
  United: "MileagePlus",
  American: "AAdvantage",
  Southwest: "Rapid Rewards",
};

interface CreateFlightBookingInput {
  flightNumber: string;
  departureDateTime: string;
  passengers: Passenger[];
  flightClass: string;
  status: "CONFIRMED" | "PENDING" | "CANCELLED";
  loyaltyInfo?: string;
}

async function createFlightBooking(
  tenantId: string,
  input: CreateFlightBookingInput
): Promise<FlightBooking> {
  const dynamoDB = await getDynamoDbClient(tenantId);
  const bookingId = faker.string.alphanumeric({
    length: 6,
    casing: "upper",
  });

  const booking: FlightBooking = {
    PK: `${tenantId}`,
    SK: `BOOKING#FLIGHT#${bookingId}`,
    TenantID: tenantId,
    BookingID: bookingId,
    Class: input.flightClass,
    Type: "FLIGHT",
    Status: input.status,
    BookingDate: new Date().toISOString(),
    FlightNumber: input.flightNumber,
    DepartureDateTime: input.departureDateTime,
    Passengers: input.passengers,
    LoyaltyInfo: input.loyaltyInfo,
  };

  const params = {
    TableName: TABLE_NAME,
    Item: booking,
  };

  try {
    const command = new PutCommand(params);
    await dynamoDB.send(command);
    return booking;
  } catch (error) {
    console.error("Error creating flight booking:", error);
    throw error;
  }
}

export async function listFlights({
  origin,
  destination,
  departure,
}): Promise<CallToolResult> {
  const flightCount = 4;
  const flights: FlightInfo[] = [];

  for (let i = 0; i < flightCount; i++) {
    const duration = faker.number.int({ min: 60, max: 480 });
    const departureTime = new Date(departure);
    departureTime.setHours(faker.number.int({ min: 0, max: 23 }));

    const arrivalTime = new Date(departureTime);
    arrivalTime.setMinutes(arrivalTime.getMinutes() + duration);

    const airline = faker.helpers.arrayElement(AIRLINES);
    const distance = faker.number.int({ min: 100, max: 3000 });

    const flight: FlightInfo = {
      departure: departureTime,
      arrival: arrivalTime,
      origin: origin,
      destination: destination,
      distance: distance,
      duration: duration,
      stops: faker.number.int({ min: 0, max: 2 }),
      flightNumber: `${faker.string.alpha({
        length: 2,
        casing: "upper",
      })}${faker.number.int({ min: 1000, max: 9999 })}`,
      airline: airline,
      availableSeats: FLIGHT_CLASSES.map((cls) => ({
        flightClass: cls,
        count: faker.number.int({ min: 0, max: 50 }),
        price: faker.number.int({ min: 100, max: 2000 }),
      })),
      frequentFlyerInfo: {
        programName: FREQUENT_FLYER_PROGRAMS[airline],
        milesEarned: Math.round(distance * 0.5),
        tierPointsEarned: Math.round(distance * 0.1),
      },
    };
    flights.push(flight);
  }

  return {
    isError: false,
    content: [
      {
        type: "text",
        text: JSON.stringify(flights),
      },
    ],
  };
}

export async function bookFlight({
  flightNumber,
  departure,
  flightClass,
  frequentFlyerNumber,
}: {
  flightNumber: string;
  departure: Date;
  flightClass: string;
  frequentFlyerNumber?: string;
}) {
  const tenantId = httpContext.get("tenantId");

  // await new Promise((resolve) => setTimeout(resolve, 1000));

  const scenario = 1; //faker.number.int({ min: 1, max: 3 });

  switch (scenario) {
    case 1:
      // Successful booking
      const booking = await createFlightBooking(tenantId, {
        departureDateTime: departure.toString(),
        flightNumber: flightNumber,
        flightClass: flightClass,
        passengers: [
          {
            Name: faker.person.fullName(),
            Seat: faker.airline.seat(),
          },
        ],
        status: "CONFIRMED",
        loyaltyInfo: frequentFlyerNumber
          ? `Frequent Flyer: ${frequentFlyerNumber}`
          : undefined,
      });

      const frequentFlyerMessage = frequentFlyerNumber
        ? `Frequent Flyer number ${frequentFlyerNumber} has been added to your booking.`
        : "";

      return {
        isError: false,
        content: [
          {
            type: "text",
            text: `Booking successful! Your confirmation number is ${booking.BookingID}. ${frequentFlyerMessage}`,
          },
        ],
      };

    case 2:
      // Credit card denied
      return {
        isError: true,
        content: [
          {
            type: "text",
            text: "ERROR: Credit card payment was declined. Please try a different payment method.",
          },
        ],
      };

    case 3:
      // Flight sold out
      return {
        isError: true,
        content: [
          {
            type: "text",
            text: "ERROR: We apologize, but this flight has sold out while processing your booking.",
          },
        ],
      };
  }
}
