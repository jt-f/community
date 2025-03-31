## RabbitMQ
docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4.0-management
# management / observability
http://localhost:15672/#/

# Websocket server
source ~/.bashrc
poetry run python src/server.py

# frontend
npm run dev

# message routing broker
source ~/.bashrc
poetry run python src/broker.py 

# agents
source ~/.bashrc
poetry run python src/agent.py --name "MyAgent2"