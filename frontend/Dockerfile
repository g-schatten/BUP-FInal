FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

EXPOSE 5173
ENV VITE_BACKEND_URL=http://backend:8000
CMD ["npm", "run", "dev"]
