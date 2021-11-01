pipeline {

    agent none

    stages {

        stage('CI') { 

            agent {
                docker {
                    label 'open_jenkins'
                    image 'python:3.8-slim'
                    args '-u root:root -v /var/run/docker.sock:/var/run/docker.sock'
                    reuseNode true
                }
            }

            environment {
                AWS_SHARED_CREDENTIALS_FILE = credentials('jenkins-aws-sandbox-config');
                ENVIRONMENT = 'sandbox';
            }

            stages {

                stage('Build and package image to ECR') {

                    steps {
                        echo 'Installing AWS Serverless Application Model SAM'
                        sh 'pip3 install aws-sam-cli awscli'
                        echo 'Building Lambda'
                        sh 'sam build --config-env ${ENVIRONMENT} --use-container'
                        echo 'Storing image in Elastic Container Registry ECR'
                        sh 'sam package --config-env ${ENVIRONMENT} --resolve-s3 --output-template-file packaged.yaml'
                    }
                }

                stage('Deploy to sandbox') {
                    steps {
                        echo 'Deploying to sandbox'
                        sh 'sam deploy --config-env ${ENVIRONMENT} --template-file packaged.yaml --no-confirm-changeset --no-fail-on-empty-changeset' 
                    }
                }
            }
        }

        stage('CD') {
            // not implemented 
            when {
                branch 'master'
            }
            stages {
                stage('QA Deployment') {
                    environment {
                        AWS_SHARED_CREDENTIALS_FILE = credentials('jenkins-aws-qa-config');  // Fix me
                        ENVIRONMENT = 'qa';
                    }
                    steps {
                        echo 'not implemented'
                    }
                }
            }
        }
    }
}
