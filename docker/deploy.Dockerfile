FROM python:3.8-slim

COPY . /code

WORKDIR /code

RUN python -m pip install --upgrade pip
RUN pip install -r requirements.txt

RUN pip install aws-sam-cli awscli

ARG ACCESS_KEY_ID
ARG SECRET_ACCESS_KEY
ARG AWS_REGION
ARG ENVIRONMENT

ENV AWS_ACCESS_KEY_ID=${ACCESS_KEY_ID}
ENV AWS_SECRET_ACCESS_KEY=${SECRET_ACCESS_KEY}
ENV AWS_REGION=${AWS_REGION}


RUN echo "Building package and uploading image to ECR"
RUN sam package \
    --config-env ${ENVIRONMENT} \
    --resolve-s3 \
    --output-template-file packaged.yaml

RUN echo "Deploying to AWS"
RUN sam deploy \
    --config-env ${ENVIRONMENT} \
    --template-file packaged.yaml 
