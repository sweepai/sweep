pipeline {
    agent any

    stages {
        stage('Clone repository') {
            steps {
                // Replace 'your-credentials-id' with the ID of your GitHub credentials in Jenkins
                // Replace 'your-repo-url' with the URL of your GitHub repository
                checkout([$class: 'GitSCM', branches: [[name: '*/main']], doGenerateSubmoduleConfigurations: false, extensions: [], submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'your-credentials-id', url: 'your-repo-url']]])
            }
        }

        stage('Build project') {
            steps {
                // Replace this with the command to build your project
                sh 'echo Building project...'
            }
        }

        stage('Build Docker image') {
            steps {
                // Replace 'your-image-name' with the name of your Docker image
                sh 'docker build -t your-image-name .'
            }
        }
    }
}