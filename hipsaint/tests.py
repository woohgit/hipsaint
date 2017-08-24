import sys
import unittest
import mock
from datetime import datetime
import json
from .messages import HipchatMessage
from .card import Card, ICON_URL


def setup_mock_request(mock_method, status_code, json_data):
    mock_response = mock.Mock()
    mock_response.read.return_value = json.dumps(json_data)
    mock_response.getcode.return_value = status_code
    mock_method.return_value = mock_response


def mock_hipchat_ok_request(mock_method):
    data = {'status': 'sent'}
    return setup_mock_request(mock_method, 200, data)


def mock_hipchat_error_request(mock_method):
    data = {'error': {'message': 'some test error', 'type': 'Unauthorized', 'code': 401}}
    return setup_mock_request(mock_method, 401, data)


class MessageTest(unittest.TestCase):
    def setUp(self):
        #"$HOSTNAME$|$LONGDATETIME$|$NOTIFICATIONTYPE$|$HOSTADDRESS$|$HOSTSTATE$|$HOSTOUTPUT$"
        self.host_inputs = 'hostname|%(longdatetime)s|%(notificationtype)s|127.0.0.1|' \
                           '%(hoststate)s|NAGIOS_OUTPUT'
        #"$SERVICEDESC$|$HOSTALIAS$|$LONGDATETIME$|$NOTIFICATIONTYPE$|$HOSTADDRESS$|$SERVICESTATE$
        # |$SERVICEOUTPUT$"
        self.service_inputs = 'servicedesc|hostalias|%(longdatetime)s|%(notificationtype)s|' \
                              '127.0.0.1|%(servicestate)s|NAGIOS_OUTPUT'

    @mock.patch('hipsaint.messages.urlopen')
    def test_ok_payload_delivery(self, mock_get):
        mock_hipchat_ok_request(mock_get)
        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'PROBLEM',
                                         'hoststate': 'DOWN'}
        msg = HipchatMessage('host', msg_inputs,
                             None, None, None, False, None, None, proxy='example.com')
        response = msg.deliver_payload()
        self.assertEqual(response.getcode(), 200)
        response_data = json.load(response)
        self.assertEqual(response_data['status'], 'sent')

    @mock.patch('hipsaint.messages.urlopen')
    def test_error_payload_delivery(self, mock_get):
        mock_hipchat_error_request(mock_get)
        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'PROBLEM',
                                         'hoststate': 'DOWN'}
        problem_msg = HipchatMessage('host', msg_inputs, None, None, None, False, None, None)
        response = problem_msg.deliver_payload()
        response_data = json.load(response)
        self.assertEqual(response.getcode(), 401)
        self.assertTrue('error' in response_data)

    @mock.patch('hipsaint.messages.urlopen')
    def test_custom_host(self, mock_get):
        mock_hipchat_ok_request(mock_get)
        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'PROBLEM',
                                         'hoststate': 'DOWN'}
        msg = HipchatMessage('host', msg_inputs, None, None, None, False, 'example.com', None)
        self.assertEqual(msg.url, 'https://example.com/v1/rooms/message')
        msg = HipchatMessage('host', msg_inputs, None, None, None, False, None, None)
        self.assertEqual(msg.url, 'https://api.hipchat.com/v1/rooms/message')

    @mock.patch('hipsaint.messages.urlopen')
    def test_api_v2(self, mock_get):
        mock_hipchat_ok_request(mock_get)
        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'PROBLEM',
                                         'hoststate': 'DOWN'}
        msg = HipchatMessage('host', msg_inputs, 'authtoken', None, 'testroom', False, 'example.com', '2')
        self.assertEqual(msg.url, 'https://example.com/v2/room/testroom/notification')
        self.assertEqual(msg.deliver_payload, msg.deliver_payload_v2)
        response = msg.deliver_payload()
        self.assertEqual(response.getcode(), 200)
        response_data = json.load(response)
        self.assertEqual(response_data['status'], 'sent')
        # verify that data that was submitted
        args = mock_get.call_args
        request = args[0][0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer authtoken')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        if sys.version_info[0] >= 3 and sys.version_info[1] >= 1:
            body = request.data
        else:
            body = request.get_data()
        data = json.loads(body.decode('utf-8'))
        self.assertTrue('color' in data)
        self.assertTrue('message' in data)
        self.assertTrue('notify' in data)
        self.assertTrue('message_format' in data)
        self.assertEqual(data['color'], 'red')
        self.assertTrue('PROBLEM' in data['message'])
        self.assertEqual(data['notify'], False)
        self.assertEqual(data['message_format'], 'html')

    def test_render_host(self):
        message_type = 'host'
        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'PROBLEM',
                                         'hoststate': 'DOWN'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'red')

        # Test short host
        problem_msg = HipchatMessage('short-host', msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'red')

        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'RECOVERY',
                                         'hoststate': 'UP'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'green')

        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'UNREACHABLE',
                                         'hoststate': 'UKNOWN'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'red')

        msg_inputs = self.host_inputs % {'longdatetime': datetime.now(),
                                         'notificationtype': 'ACKNOWLEDGEMENT',
                                         'hoststate': 'DOWN'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'purple')

    def test_render_service(self):
        message_type = 'service'
        msg_inputs = self.service_inputs % {'longdatetime': datetime.now(),
                                            'notificationtype': 'PROBLEM',
                                            'servicestate': 'WARNING'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'yellow')

        msg_inputs = self.service_inputs % {'longdatetime': datetime.now(),
                                            'notificationtype': 'PROBLEM',
                                            'servicestate': 'CRITICAL'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'red')

        # Test short service
        problem_msg = HipchatMessage('short-service', msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'red')

        msg_inputs = self.service_inputs % {'longdatetime': datetime.now(),
                                            'notificationtype': 'PROBLEM',
                                            'servicestate': 'UNKNOWN'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'gray')

        msg_inputs = self.service_inputs % {'longdatetime': datetime.now(),
                                            'notificationtype': 'RECOVERY',
                                            'servicestate': 'OK'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'green')

        msg_inputs = self.service_inputs % {'longdatetime': datetime.now(),
                                            'notificationtype': 'ACKNOWLEDGEMENT',
                                            'servicestate': 'CRITICAL'}
        problem_msg = HipchatMessage(message_type, msg_inputs, None, None, None, False, None, None)
        problem_msg.render_message()
        self.assertEqual(problem_msg.message_color, 'purple')


class CardTest(unittest.TestCase):

    def setUp(self):
        # "$HOSTNAME$|$LONGDATETIME$|$NOTIFICATIONTYPE$|$HOSTADDRESS$|$HOSTSTATE$|$HOSTOUTPUT$"
        self.host_inputs = 'hostname|%(longdatetime)s|%(notificationtype)s|127.0.0.1|' \
                '%(hoststate)s|NAGIOS_OUTPUT'

        self.service_inputs = 'servicedesc|hostalias|%(longdatetime)s|%(notificationtype)s|' \
                              '127.0.0.1|%(servicestate)s|NAGIOS_OUTPUT'

    def test_card_attributes(self):
        parameters = {
            'PROBLEM1': {
                'ntype': 'PROBLEM',
                'state': 'CRITICAL',
                'style': 'lozenge-error'},
            'PROBLEM2': {
                'ntype': 'PROBLEM',
                'state': 'WARNING',
                'style': 'lozenge-current'},
            'PROBLEM3': {
                'ntype': 'PROBLEM',
                'state': 'DOWN',
                'style': 'lozenge-error'},
            'RECOVERY1': {
                'ntype': 'RECOVERY',
                'state': 'OK',
                'style': 'lozenge-success'},
            'RECOVERY2': {
                'ntype': 'RECOVERY',
                'state': 'UP',
                'style': 'lozenge-success'},
            'PROBLEM4': {
                'ntype': 'PROBLEM',
                'state': 'UNREACHABLE',
                'style': 'lozenge-error'},
            'ACKNOWLEDGEMENT': {
                'ntype': 'ACKNOWLEDGEMENT',
                'state': 'DOWN',
                'style': 'lozenge-error'}}

        for p in parameters:
            msg_inputs = self.host_inputs % {
                'longdatetime': datetime.now(),
                'notificationtype': parameters[p]['ntype'],
                'hoststate': parameters[p]['state']}

            card = Card(msg_inputs, 'host')
            attributes = [
                {
                    'value': {
                        'label': parameters[p]['ntype']
                    },
                    'label': 'Type'
                },
                {
                    'value': {
                        'label': parameters[p]['state'],
                        'style': parameters[p]['style']
                    },
                    'label': 'State'
                },
                {
                    'value': {
                        'label': '%s (%s)' % ('hostname', '127.0.0.1')
                    },
                    'label': 'Host'
                }]
            self.assertEqual(card.get_attributes(), attributes)

    def test_card_activity(self):
        timestamp = datetime.now()
        parameters = {
            'PRO': {
                'ntype': 'PROBLEM',
                'state': 'CRITICAL',
                'style': 'lozenge-error',
                'timestamp': timestamp},
            'REC': {
                'ntype': 'RECOVERY',
                'state': 'OK',
                'style': 'lozenge-success',
                'timestamp': timestamp},
            'ACK': {
                'ntype': 'ACKNOWLEDGEMENT',
                'state': 'CRITICAL',
                'style': 'lozenge',
                'timestamp': timestamp},
            'FLIPSTART': {
                'ntype': 'FLAPPINGSTART',
                'state': 'CRITICAL',
                'style': 'lozenge-current',
                'timestamp': timestamp},
            'DOWNTIMESTART': {
                'ntype': 'DOWNTIMESTART',
                'state': 'CRITICAL',
                'style': 'lozenge-error',
                'timestamp': timestamp}
        }

        for p in parameters:
            msg_inputs = self.host_inputs % {
                'longdatetime': timestamp,
                'notificationtype': parameters[p]['ntype'],
                'hoststate': parameters[p]['state']}

            card = Card(msg_inputs, 'host')
            activity = {
                'html': '<b>hostname</b> (%(hostaddress)s) - <span class="aui-lozenge aui-%(style)s">%(ntype)s</span>' % {
                    'hostaddress': '127.0.0.1',
                    'style': parameters[p]['style'],
                    'ntype': parameters[p]['ntype']},
                'icon': ICON_URL}
            self.assertEqual(card.get_activity(), activity)

            msg_inputs = self.service_inputs % {
                'longdatetime': timestamp,
                'notificationtype': parameters[p]['ntype'],
                'servicestate': parameters[p]['state']}

            card = Card(msg_inputs, 'service')
            activity = {
                'html': '<b>servicedesc</b> on hostalias (%(hostaddress)s) - <span class="aui-lozenge aui-%(style)s">%(ntype)s</span>' % {
                    'hostaddress': '127.0.0.1',
                    'style': parameters[p]['style'],
                    'ntype': parameters[p]['ntype']},
                'icon': ICON_URL}
            self.assertEqual(card.get_activity(), activity)

    def test_card_title_and_description(self):
        timestamp = datetime.now()
        parameters = {'PRO-CRIT': {'ntype': 'PROBLEM',
                                   'state': 'CRITICAL',
                                   'style': 'lozenge-error',
                                   'timestamp': timestamp},
                      'PRO-WARN': {'ntype': 'PROBLEM',
                                   'state': 'WARNING',
                                   'style': 'lozenge-error',
                                   'timestamp': timestamp},
                      'REC': {'ntype': 'RECOVERY',
                              'state': 'OK',
                              'style': 'lozenge-success',
                              'timestamp': timestamp},
                      'UNR': {'ntype': 'UNREACHABLE',
                              'state': 'CRITICAL',
                              'style': 'lozenge-error',
                              'timestamp': timestamp},
                      'ACK': {'ntype': 'ACKNOWLEDGEMENT',
                              'state': 'CRITICAL',
                              'style': 'lozenge-error',
                              'timestamp': timestamp}}

        for p in parameters:
            msg_inputs = self.host_inputs % {
                'longdatetime': timestamp,
                'notificationtype': parameters[p]['ntype'],
                'hoststate': parameters[p]['state']}

            expected_title = '%(ntype)s - %(hostname)s (%(hostaddress)s) is %(state)s' % {
                'ntype': parameters[p]['ntype'],
                'hostname': 'hostname',
                'hostaddress': '127.0.0.1',
                'state': parameters[p]['state']
            }

            card = Card(msg_inputs, 'host')
            cardObject = card.get_card()
            self.assertEquals(cardObject['title'], expected_title)
            self.assertEquals(cardObject['description'], 'NAGIOS_OUTPUT')

    def test_service_card(self):
        timestamp = datetime.now()
        parameters = {'PRO-CRIT': {'ntype': 'PROBLEM',
                                   'state': 'CRITICAL',
                                   'style': 'lozenge-error',
                                   'timestamp': timestamp},
                      'PRO-WARN': {'ntype': 'PROBLEM',
                                   'state': 'WARNING',
                                   'style': 'lozenge-error',
                                   'timestamp': timestamp},
                      'REC': {'ntype': 'RECOVERY',
                              'state': 'OK',
                              'style': 'lozenge-success',
                              'timestamp': timestamp},
                      'UNR': {'ntype': 'UNREACHABLE',
                              'state': 'CRITICAL',
                              'style': 'lozenge-error',
                              'timestamp': timestamp},
                      'ACK': {'ntype': 'ACKNOWLEDGEMENT',
                              'state': 'CRITICAL',
                              'style': 'lozenge-error',
                              'timestamp': timestamp}}

        for p in parameters:
            msg_inputs = self.service_inputs % {
                'longdatetime': timestamp,
                'notificationtype': parameters[p]['ntype'],
                'servicestate': parameters[p]['state']}

            expected_title = '%(ntype)s - servicedesc on hostalias (%(hostaddress)s) is %(state)s' % {
                'ntype': parameters[p]['ntype'],
                'hostaddress': '127.0.0.1',
                'state': parameters[p]['state']
            }

            card = Card(msg_inputs, 'service')
            cardObject = card.get_card()

            self.assertEquals(cardObject['title'], expected_title)
            self.assertEquals(cardObject['description'], 'NAGIOS_OUTPUT')
