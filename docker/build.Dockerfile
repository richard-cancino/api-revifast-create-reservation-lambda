FROM public.ecr.aws/lambda/python:3.8

COPY ["*.py", "requirements.txt", "/var/task/"]

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD [ "app.lambda_handler" ]
