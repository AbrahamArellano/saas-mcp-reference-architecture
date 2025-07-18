import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { Readable } from "stream";
import fs from "fs/promises";
import { AuthInfo } from "../types/authInfo";

async function readTravelPolicy() {
  try {
    const policyContents = await fs.readFile("travelpolicy.txt");
    return policyContents.toString("utf-8");
  } catch (error) {
    console.error("Error reading travel policy file:", error);
    throw new Error("Failed to read travel policy");
  }
}

async function readTravelPolicyS3(tenantId: string) {
  try {
    const S3_BUCKET_NAME = process.env.BUCKET_NAME;

    const s3Client = new S3Client({
      region: process.env.AWS_DEFAULT_REGION || "us-east-1",
    });

    // Construct folder path using tenant ID
    const folderPath = `${tenantId}`;
    const bucketName = S3_BUCKET_NAME;
    const key = `${folderPath}/travelpolicy.txt`;
    console.log("S3 Bucket key", key);

    const command = new GetObjectCommand({
      Bucket: bucketName,
      Key: key,
    });

    const response = await s3Client.send(command);

    // Convert readable stream to string
    const stream = response.Body;
    if (stream instanceof Readable) {
      const chunks = [] as any[];
      for await (const chunk of stream) {
        chunks.push(chunk);
      }

      return Buffer.concat(chunks).toString("utf-8");
    }

    throw new Error("Invalid response from S3");
  } catch (error) {
    console.error("Error reading travel policy from S3:", error);
    throw new Error("Failed to read travel policy from S3");
  }
}

export async function getLocalFileTravelPolicy() {
  const policyContents = await readTravelPolicy();

  return {
    contents: [
      {
        uri: "file://travel/policy",
        mimeType: "text/plain",
        text: policyContents,
      },
    ],
  };
}

export async function getS3TravelPolicy(
  params,
  { authInfo: { tenantId } }: AuthInfo
) {
  // const tenantId = httpContext.get("tenantId");
  const policyContents = await readTravelPolicyS3(tenantId);

  return {
    contents: [
      {
        uri: "travelpolicy://tenant",
        mimeType: "text/plain",
        text: policyContents,
      },
    ],
  };
}
