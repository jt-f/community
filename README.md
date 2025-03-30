docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4.0-management
poetry run python src/server.py
poetry run python src/broker.py 
npm run dev