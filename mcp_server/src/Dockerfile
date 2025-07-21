FROM node:22-alpine
WORKDIR /app
COPY package*.json ./*.js ./tools/* ./resources/* ./services/* ./types/* *.txt /app/
RUN npm ci --verbose
COPY . .

RUN chown -R node:node /app
USER node

EXPOSE 3000
# CMD ["node", "index.js"]
CMD ["npx", "tsx", "--env-file=.env", "--watch", "index.js"]
