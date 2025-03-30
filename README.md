## RabbitMQ
docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4.0-management
# management / observability
http://localhost:15672/#/

# Websocket server
poetry run python src/server.py

# message routing broker
poetry run python src/broker.py 

# frontend
npm run dev