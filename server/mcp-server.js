import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import httpContext from "express-http-context";
import metadata from "./metadata.js";
import { listBookings } from "./tools/listBookings.js";
import { coerce, z } from "zod";
import { bookFlight, listFlights } from "./tools/manageFlights.js";
import {
  bookHotel,
  listHotels,
  modifyHotelBooking,
} from "./tools/manageHotels.js";
import { getLoyaltyProgramInfo } from "./tools/frequentFlyer.js";
import {
  getLocalFileTravelPolicy,
  getS3TravelPolicy,
} from "./resources/travelPolicy.js";

let SHORT_DELAY = true;
const LONG_DELAY_MS = 100;
const SHORT_DELAY_MS = 50;

const create = () => {
  const mcpServer = new McpServer(
    {
      name: "demo-mcp-server",
      version: metadata.version,
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  mcpServer.resource(
    "CompanyTravelPolicy",
    "file://travel/policy",
    getLocalFileTravelPolicy
  );

  mcpServer.resource(
    "CompanyTravelPolicyPerTenant",
    "travelpolicy://tenant",
    getS3TravelPolicy
  );

  mcpServer.tool(
    "list_bookings",
    "Get an overview of a user's bookings and optionally filter them by type or ID.",
    {
      id: z.optional(z.string()),
      type: z.optional(z.enum(["ALL", "HOTEL", "FLIGHT"])),
    },
    listBookings
  );

  mcpServer.tool(
    "find_flights",
    "Search for available flights between two locations on a given date.",
    {
      origin: z.string(),
      destination: z.string(),
      departure: z.string().date(),
    },
    listFlights
  );

  const tenantTier = httpContext.get("tenantTier");

  // if (tenantTier === "gold") {
  mcpServer.tool(
    "book_flight",
    "Book a flight using its flight number, departure date and time as well as the flight class and an optional frequent flyer number.",
    {
      flightNumber: z.string(),
      departure: z.string().date(),
      flightClass: z.string(),
      frequentFlyerNumber: z.optional(z.string()),
    },
    bookFlight
  );

  mcpServer.tool(
    "book_hotel",
    "Book a hotel room by providing the hotel name, check-in and check-out dates, room type, number of guests (1-10), and an optional loyalty program number",
    {
      hotelName: z.string(),
      checkIn: z.string().date(),
      checkOut: z.string().date(),
      roomType: z.string(),
      guests: coerce.number().int().min(1).max(10).default(1),
      loyaltyNumber: z.optional(z.string()),
    },
    bookHotel
  );
  // }

  mcpServer.tool(
    "list_hotels",
    "Search for available hotels in a specified city for given check-in and check-out dates, with the number of guests (1-10).",
    {
      city: z.string(),
      checkIn: z.string().date(),
      checkOut: z.string().date(),
      guests: coerce.number().int().min(1).max(10).default(1),
    },
    listHotels
  );

  // mcpServer.tool(
  //   "change_hotel_booking",
  //   {
  //     confirmationNumber: z.string(),
  //     modification: z.object({
  //       type: z.enum([
  //         "CHANGE_DATES",
  //         "UPGRADE_ROOM",
  //         "MODIFY_GUESTS",
  //         "ADD_SERVICES",
  //       ]),
  //       newCheckIn: z.optional(z.string().date()),
  //       newCheckOut: z.optional(z.string().date()),
  //       newRoomType: z.optional(z.string()),
  //       guestCount: z.optional(coerce.number().int().min(1).max(10)),
  //       additionalServices: z.optional(z.array(z.string())),
  //     }),
  //   },
  //   modifyHotelBooking
  // );

  mcpServer.tool(
    "loyalty_info",
    "Get the user's participation status in Airline and Hotel Loyalty programs",
    getLoyaltyProgramInfo
  );

  return mcpServer;
};

export default { create };
