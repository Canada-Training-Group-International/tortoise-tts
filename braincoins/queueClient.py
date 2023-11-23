import argparse
import pika
import mysql.connector
from .process_queue import tortoise_handler
import json
import requests
import os
import base64
import hashlib
from pprint import pprint

class queueClient:

    def connect_db(self, return_dict=False):
        self.mydb = mysql.connector.connect(
                host="localhost",
                user=self.db_user,
                password=self.db_password,
                database="dolphin",
                )
    
        if return_dict:
            self.mycursor = self.mydb.cursor(dictionary=True)
        else:
            self.mycursor = self.mydb.cursor()


    def retrieve_pending_tasks(self):
        self.connect_db(return_dict=True)
    
        query=""" select * from (
    select f.user_id, f.id as file_id, f.file_name, f.date_created, f.server_path, f.file_hash,
    row_number() over (partition by f.user_id order by f.date_created desc) as rn
    from security_levels sl
    inner join users u on sl.id=u.security_id
    inner join user_uploaded_files f on u.id=f.user_id
    where sl.security_level = 'Family'
    and f.file_mime_type = 'audio/mp3'
    and file_name regexp 'voice_sample_[0-9].*'
) f
where rn<=3
order by f.user_id, date_created desc; """
    
        #self.mycursor.execute(query, (,))
        self.mycursor.execute(query, ())
        tasks={}
        i =0
        for x in self.mycursor:
            if x['user_id'] not in tasks:
                tasks[x['user_id']] = {
                        'user_id': x['user_id']
                        ,'files': []
                        ,'text': 'congratulations Jimmy, you did great there champ!'
                        ,'callback_url': 'http://ed-virtualbox/api_endpoint.php'
                        ,'auth_token': x['user_id']
                        }
            tasks[x['user_id']]['files'].append({
                'file_url': 'http://ed-virtualbox/certifications_list.php?file=' + str(x['file_id']) + '&temp_pwd=' + str(x['user_id'])
                ,'file_id': x['file_id']
                ,'file_name': x['file_name']
                ,'file_hash': x['file_hash']
                })
        return tasks

    def __init__(self, environment='dev'):
        # Establish a connection to the RabbitMQ server
        local = False
        if local:
            self.connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        else:
            credentials = pika.PlainCredentials('rabbit_user', '1234')
            dev_queue_server = 'ed-virtualbox'
            prd_queue_server = 'braincoins.org'
            prd_queue_server = '35.89.145.13'
            queue_server = dev_queue_server if environment == 'dev' else prd_queue_server
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(queue_server, 5672, '/', credentials ))

        self.channel = self.connection.channel()

        if environment == 'prd':
            self.db_user="root"
            self.db_password="Dolphin87!"
        else:
            self.db_user="dolphinUser"
            self.db_password="d0lph1n"

    def createQueue(self, queueName):
        # Create a queue
        self.channel.queue_declare(queue=queueName)

    def sendMessage(self, queueName, message):
        # Publish a message to the queue
        self.channel.basic_publish(exchange='', routing_key=queueName, body=message)

    def waitForMessages(self, queueName):
        self.channel.basic_consume(queue=queueName, on_message_callback=self.callback, auto_ack=True)
        self.channel.start_consuming()
        print('Waiting for messages. To exit, press CTRL+C')

    def __del__(self):
        # Close the connection
        if self.connection:    
            self.connection.close()

    def callback(self, ch, method, properties, body):
        try:
            str_body = body.decode('utf-8')
            print(f"Received: {body}")
            print(f"Received: {str_body}")
            json_body = json.loads(str_body)
            pprint(json_body)
            #voice= 'geralt'
            text = json_body['text']
            files = json_body['files']
            voice = 'user_' + str(json_body['user_id'])
            for file in files:
                path = os.path.join(r'tortoise\voices', voice)
                if not os.path.exists(path):
                    os.makedirs(path)

                #set_trace()
                if os.path.exists(os.path.join(path, file['file_name'])):
                    with open(os.path.join(path, file['file_name']), 'rb') as handler:
                        md5 = hashlib.md5(handler.read()).hexdigest()
                        print(f"Existing file md5: {md5}")
                        if md5 == file['file_hash']:
                            print("File already exists")
                            continue

                file_url = file['file_url']
                print(f"dowloading file: {file_url}")
                content = requests.get(file_url).content

                with open(os.path.join(path, file['file_name']), 'wb') as handler:
                    handler.write(content)

            output_file_name = json_body['output_file_name'].split('.')[0] + '.wav'
            is_test = False
            #is_test = True
            if is_test:
                output_files = [
                    r'results\longform\user_411\custom_voice_sample.wav'
                    ]
            else:
                output_files = tortoise_handler(voice, text, output_file_name)
            print(output_files)
            #set_trace()
            for out_file in output_files:
                with open(out_file, 'rb') as f:
                    data = f.read()
                    file_name = os.path.basename(out_file)
                    #set_trace()
                    response = {
                            'action': 'saveUserFile'
                            ,'auth_token': json_body['auth_token']
                            ,'file_name': output_file_name
                            ,'file_content': base64.b64encode(data).decode('utf-8')
                            ,'file_type': 'audio/wav'
                            ,'file_group': 'event'

                            ,'user_id': json_body['user_id']
                            ,'event_id': json_body['event_id']
                            ,'text': text

                            }
                    #send over an ajax request
                    result = requests.post(json_body['callback_url'], json=response)
                    print(result)
                    json_result = result.json()
                    json_result['request']['POST']['file_content'] = '...'
                    print(json.dumps(json_result, indent=4)[0:5002])
                    #print(result.text)
        except Exception as e:
            print('Error in processing message')
            print(e)



if __name__ == '__main__':
    from IPython.core.debugger import set_trace
    #set_trace()

    parser = argparse.ArgumentParser(description='Queue Client.')
    parser.add_argument('message', nargs='?', default=None)
    #parser.add_argument('command', nargs='?', choices=['listen', 'send'], default='send',
    #                    help='Command: "listen" or "send" (default is "send")')
    #parser.add_argument('--listen', default=None, help='')
    parser.add_argument('-l', '--listen', action='store_true', help='Listen for messages')
    parser.add_argument('-p', '--process', action='store_true', help='Process pending tasks')
    
    args = parser.parse_args()
    print(args)

    env = 'dev'
    #env = 'prd'
    client = queueClient(env)
    queueName = 'customTextToSpeach'
    client.createQueue(queueName)
    if args.listen:
        client.waitForMessages('')
    elif args.process:
        tasks = client.retrieve_pending_tasks()
        #print(tasks)
        for task in tasks:
            json_task = json.dumps(tasks[task])
            print(json_task)
            client.sendMessage(queueName, json_task)
    elif args.message:
        client.sendMessage(queueName, args.message)





