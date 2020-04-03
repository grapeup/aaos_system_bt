#
#   Copyright 2019 - The Android Open Source Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import time
from datetime import timedelta

from mobly import asserts

from bluetooth_packets_python3 import l2cap_packets
from bluetooth_packets_python3 import RawBuilder
from bluetooth_packets_python3.l2cap_packets import Final
from bluetooth_packets_python3.l2cap_packets import Poll
from bluetooth_packets_python3.l2cap_packets import SegmentationAndReassembly
from bluetooth_packets_python3.l2cap_packets import SupervisoryFunction
from cert.gd_base_test import GdBaseTestClass
from cert.matchers import L2capMatchers
from cert.metadata import metadata
from cert.py_l2cap import PyL2cap
from cert.truth import assertThat
from facade import common_pb2
from google.protobuf import empty_pb2 as empty_proto
from l2cap.classic import facade_pb2 as l2cap_facade_pb2
from l2cap.classic.cert.cert_l2cap import CertL2cap
from l2cap.classic.facade_pb2 import RetransmissionFlowControlMode
from neighbor.facade import facade_pb2 as neighbor_facade

# Assemble a sample packet.
SAMPLE_PACKET = RawBuilder([0x19, 0x26, 0x08, 0x17])


class L2capTest(GdBaseTestClass):

    def setup_class(self):
        super().setup_class(dut_module='L2CAP', cert_module='HCI_INTERFACES')

    def setup_test(self):
        super().setup_test()

        self.dut.address = self.dut.hci_controller.GetMacAddressSimple()
        self.cert.address = self.cert.controller_read_only_property.ReadLocalAddress(
            empty_proto.Empty()).address
        self.cert_address = common_pb2.BluetoothAddress(
            address=self.cert.address)

        self.dut_l2cap = PyL2cap(self.dut, self.cert_address)
        self.cert_l2cap = CertL2cap(self.cert)

    def teardown_test(self):
        self.cert_l2cap.close()
        self.dut_l2cap.close()
        super().teardown_test()

    def cert_send_b_frame(self, b_frame):
        self.cert_l2cap.send_acl(b_frame)

    def _setup_link_from_cert(self):
        self.dut.neighbor.EnablePageScan(
            neighbor_facade.EnableMsg(enabled=True))
        self.cert_l2cap.connect_acl(self.dut.address)

    def _open_unvalidated_channel(self,
                                  signal_id=1,
                                  scid=0x0101,
                                  psm=0x33,
                                  mode=RetransmissionFlowControlMode.BASIC):

        dut_channel = self.dut_l2cap.register_dynamic_channel(psm, mode)
        cert_channel = self.cert_l2cap.open_channel(signal_id, psm, scid)

        return (dut_channel, cert_channel)

    def _open_channel(self,
                      signal_id=1,
                      scid=0x0101,
                      psm=0x33,
                      mode=RetransmissionFlowControlMode.BASIC):
        result = self._open_unvalidated_channel(signal_id, scid, psm, mode)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse(),
            L2capMatchers.ConfigurationRequest()).inAnyOrder()

        return result

    def _open_channel_from_dut(self,
                               psm=0x33,
                               mode=RetransmissionFlowControlMode.BASIC):
        dut_channel_future = self.dut_l2cap.connect_dynamic_channel_to_cert(
            psm, mode)
        cert_channel = self.cert_l2cap.verify_and_respond_open_channel_from_remote(
            psm)
        dut_channel = dut_channel_future.get_channel()

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse(),
            L2capMatchers.ConfigurationRequest()).inAnyOrder()

        return (dut_channel, cert_channel)

    def test_connect_dynamic_channel_and_send_data(self):
        self._setup_link_from_cert()

        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(L2capMatchers.Data(b'abc'))

    def test_receive_packet_from_unknown_channel(self):
        self._setup_link_from_cert()

        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)

        i_frame = l2cap_packets.EnhancedInformationFrameBuilder(
            0x99, 0, Final.NOT_SET, 1,
            l2cap_packets.SegmentationAndReassembly.UNSEGMENTED, SAMPLE_PACKET)
        self.cert_l2cap.send_acl(i_frame)
        assertThat(cert_channel).emitsNone(
            L2capMatchers.SFrame(req_seq=4), timeout=timedelta(seconds=1))

    def test_open_two_channels(self):
        self._setup_link_from_cert()

        self._open_channel(signal_id=1, scid=0x41, psm=0x41)
        self._open_channel(signal_id=2, scid=0x43, psm=0x43)

    def test_connect_and_send_data_ertm_no_segmentation(self):
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc' * 34)
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc' * 34))

        cert_channel.send_i_frame(tx_seq=0, req_seq=1, payload=SAMPLE_PACKET)
        # todo verify received?

    @metadata(
        pts_test_id="L2CAP/COS/CED/BV-01-C", pts_test_name="Request Connection")
    def test_basic_operation_request_connection(self):
        """
        Verify that the IUT is able to request the connection establishment for
        an L2CAP data channel and initiate the configuration procedure.
        """
        self._setup_link_from_cert()
        (dut_channel, cert_channel) = self._open_channel_from_dut(psm=0x33)

    @metadata(pts_test_id="L2CAP/COS/CED/BV-03-C", pts_test_name="Send data")
    def test_send_data(self):
        """
        Verify that the IUT is able to send DATA
        """
        self._setup_link_from_cert()

        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)
        dut_channel.send(b'hello')
        assertThat(cert_channel).emits(L2capMatchers.Data(b'hello'))

    @metadata(pts_test_id="L2CAP/COS/CED/BV-04-C", pts_test_name="Disconnect")
    def test_disconnect(self):
        """
        Verify that the IUT is able to disconnect the data channel
        """
        self._setup_link_from_cert()

        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)
        dut_channel.close_channel()
        cert_channel.verify_disconnect_request()

    @metadata(
        pts_test_id="L2CAP/COS/CED/BV-05-C", pts_test_name="Accept connection")
    def test_accept_connection(self):
        """
        Also verify that DUT can send 48 bytes PDU (minimal MTU)
        """
        self._setup_link_from_cert()

        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)
        dut_channel.send(b'a' * 48)
        assertThat(cert_channel).emits(L2capMatchers.Data(b'a' * 48))

    @metadata(
        pts_test_id="L2CAP/COS/CED/BV-07-C", pts_test_name="Accept Disconnect")
    def test_accept_disconnect(self):
        """
        Verify that the IUT is able to respond to the request to disconnect the
        data channel
        """
        self._setup_link_from_cert()

        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)
        cert_channel.disconnect_and_verify()

    @metadata(
        pts_test_id="L2CAP/COS/CED/BV-08-C",
        pts_test_name="Disconnect on Timeout")
    def test_disconnect_on_timeout(self):
        """
        Verify that the IUT disconnects the data channel and shuts down this
        channel if no response occurs
        """
        self._setup_link_from_cert()
        self.cert_l2cap.ignore_config_and_connections()

        self._open_unvalidated_channel(scid=0x41, psm=0x33)

        assertThat(self.cert_l2cap.get_control_channel()).emitsNone(
            L2capMatchers.ConfigurationResponse())

    @metadata(
        pts_test_id="L2CAP/COS/CFD/BV-01-C", pts_test_name="Continuation Flag")
    def test_continuation_flag(self):
        """
        Verify the IUT is able to receive configuration requests that have the
        continuation flag set
        """
        cert_acl_handle = self._setup_link_from_cert()

        # Send configuration request with CONTINUE
        self.cert_l2cap.reply_with_continuation_flag()

        (dut_channel, cert_channel) = self._open_unvalidated_channel(
            scid=0x41, psm=0x33)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse(), at_least_times=2)

    @metadata(
        pts_test_id="L2CAP/COS/CFD/BV-02-C",
        pts_test_name="Negotiation with Reject")
    def test_retry_config_after_rejection(self):
        """
        Verify that the IUT is able to perform negotiation while the Lower
        Tester rejects the proposed configuration parameter values
        """
        self._setup_link_from_cert()

        self.cert_l2cap.reply_with_unacceptable_parameters()

        self._open_unvalidated_channel(scid=0x41, psm=0x33)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse(),
            L2capMatchers.ConfigurationRequest()).inAnyOrder()
        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationRequest())

    @metadata(
        pts_test_id="L2CAP/COS/CFD/BV-03-C",
        pts_test_name="Send Requested Options")
    def test_send_requested_options(self):
        """
        Verify that the IUT can receive a configuration request with no options
        and send the requested options to the Lower Tester
        """
        self._setup_link_from_cert()
        (dut_channel, cert_channel) = self._open_channel(scid=0x41, psm=0x33)

    @metadata(
        pts_test_id="L2CAP/COS/CFD/BV-08-C",
        pts_test_name="Non-blocking Config Response")
    def test_non_blocking_config_response(self):
        """
        Verify that the IUT does not block transmitting L2CAP_ConfigRsp while
        waiting for L2CAP_ConfigRsp from the Lower Tester
        """
        self._setup_link_from_cert()

        self.cert_l2cap.ignore_config_request()

        self._open_unvalidated_channel(scid=0x41, psm=0x33)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse(),
            L2capMatchers.ConfigurationRequest()).inAnyOrder()

    @metadata(
        pts_test_id="L2CAP/COS/CFD/BV-12-C",
        pts_test_name="Unknown Option Response")
    def test_config_unknown_options_with_hint(self):
        """
        Verify that the IUT can give the appropriate error code when the Lower
        Tester proposes any number of unknown options that are optional
        """
        self._setup_link_from_cert()
        self.cert_l2cap.reply_with_unknown_options_and_hint()

        self._open_unvalidated_channel(scid=0x41, psm=0x33)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse())

    @metadata(
        pts_test_id="L2CAP/COS/ECH/BV-01-C",
        pts_test_name="Respond to Echo Request")
    def test_respond_to_echo_request(self):
        """
        Verify that the IUT responds to an echo request.
        """
        self._setup_link_from_cert()
        echo_request = l2cap_packets.EchoRequestBuilder(100,
                                                        RawBuilder([1, 2, 3]))
        self.cert_l2cap.get_control_channel().send(echo_request)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.PartialData(b"\x01\x02\x03"))

    @metadata(
        pts_test_id="L2CAP/COS/CED/BI-01-C",
        pts_test_name="Reject Unknown Command")
    def test_reject_unknown_command(self):
        """
        Verify that the IUT rejects an unknown signaling command
        """
        self._setup_link_from_cert()

        # Command code ff, Signal id 01, size 0000
        invalid_command_packet = RawBuilder([0xff, 0x01, 0x00, 0x00])
        self.cert_l2cap.get_control_channel().send(invalid_command_packet)

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.CommandReject())

    @metadata(
        pts_test_id="L2CAP/COS/IEX/BV-02-C",
        pts_test_name="Respond with 1.2 Features")
    def test_respond_with_1_2_features(self):
        """
        Verify that the IUT responds to an information request command
        soliciting for Specification 1.2 features
        """
        self._setup_link_from_cert()
        control_channel = self.cert_l2cap.get_control_channel()

        control_channel.send_extended_features_request()

        assertThat(control_channel).emits(
            L2capMatchers.InformationResponseExtendedFeatures())

    @metadata(
        pts_test_id="L2CAP/EXF/BV-01-C",
        pts_test_name="Extended Features Information Response for "
        "Enhanced Retransmission Mode")
    def test_extended_feature_info_response_ertm(self):
        """
        Verify the IUT can format an Information Response for the information
        type of Extended Features that correctly identifies that Enhanced
        Retransmission Mode is locally supported
        """
        self._setup_link_from_cert()
        control_channel = self.cert_l2cap.get_control_channel()

        control_channel.send_extended_features_request()

        assertThat(control_channel).emits(
            L2capMatchers.InformationResponseExtendedFeatures(
                supports_ertm=True))

    @metadata(
        pts_test_id="L2CAP/EXF/BV-02-C",
        pts_test_name="Extended Features Information Response for "
        "Streaming Mode")
    def test_extended_feature_info_response_streaming(self):
        """
        Verify the IUT can format an Information Response for the information
        type of Extended Features that correctly identifies that Streaming Mode
        is locally supported
        """
        asserts.skip("Streaming not supported")
        self._setup_link_from_cert()
        control_channel = self.cert_l2cap.get_control_channel()

        control_channel.send_extended_features_request()

        assertThat(control_channel).emits(
            L2capMatchers.InformationResponseExtendedFeatures(
                supports_streaming=True))

    @metadata(
        pts_test_id="L2CAP/EXF/BV-03-C",
        pts_test_name="Extended Features Information Response for FCS "
        "Option")
    def test_extended_feature_info_response_fcs(self):
        """
        Verify the IUT can format an Information Response for the information
        type of Extended Features that correctly identifies that the FCS Option
        is locally supported.

        Note: This is not mandated by L2CAP Spec
        """
        self._setup_link_from_cert()
        control_channel = self.cert_l2cap.get_control_channel()

        control_channel.send_extended_features_request()

        assertThat(control_channel).emits(
            L2capMatchers.InformationResponseExtendedFeatures(
                supports_fcs=True))

    @metadata(
        pts_test_id="L2CAP/EXF/BV-05-C",
        pts_test_name="Extended Features Information Response for Fixed "
        "Channels")
    def test_extended_feature_info_response_fixed_channels(self):
        """
        Verify the IUT can format an Information Response for the information
        type of Extended Features that correctly identifies that the Fixed
        Channels option is locally supported
        """
        asserts.skip("Fixed channel is not supported")

        self._setup_link_from_cert()
        control_channel = self.cert_l2cap.get_control_channel()

        control_channel.send_extended_features_request()

        assertThat(control_channel).emits(
            L2capMatchers.InformationResponseExtendedFeatures(
                supports_fixed_channels=True))

    @metadata(
        pts_test_id="L2CAP/FOC/BV-01-C",
        pts_test_name="IUT Initiated Configuration of the FCS Option")
    def test_config_channel_not_use_FCS(self):
        """
        Verify the IUT can configure a channel to not use FCS in I/S-frames.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'))

    @metadata(
        pts_test_id="L2CAP/FOC/BV-02-C",
        pts_test_name="Lower Tester Explicitly Requests FCS should be "
        "Used")
    def test_explicitly_request_use_FCS(self):
        """
        Verify the IUT will include the FCS in I/S-frames if the Lower Tester
        explicitly requests that FCS should be used
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()
        self.cert_l2cap.turn_on_fcs()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrameWithFcs(payload=b"abc"))

    @metadata(
        pts_test_id="L2CAP/FOC/BV-03-C",
        pts_test_name="Lower Tester Implicitly Requests FCS should be "
        "Used")
    def test_implicitly_request_use_FCS(self):
        """
        Verify the IUT will include the FCS in I/S-frames if the Lower Tester
        implicitly requests that FCS should be used.

        TODO: Update this test case. What's the difference between this one and
        TODO: test_explicitly_request_use_FCS?
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()
        self.cert_l2cap.turn_on_fcs()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrameWithFcs(payload=b"abc"))

    @metadata(
        pts_test_id="L2CAP/OFS/BV-01-C",
        pts_test_name="Sending I-Frames without FCS for ERTM")
    def test_sending_i_frames_without_fcs_for_ertm(self):
        """
        Verify the IUT does not include the FCS in I-frames.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b"abc"))

    @metadata(
        pts_test_id="L2CAP/OFS/BV-02-C",
        pts_test_name="Receiving I-Frames without FCS for ERTM")
    def test_receiving_i_frames_without_fcs_for_ertm(self):
        """
        Verify the IUT can handle I-frames that do not contain the FCS.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b"abc")
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b"abc"))

    @metadata(
        pts_test_id="L2CAP/OFS/BV-05-C",
        pts_test_name="Sending I-Frames with FCS for ERTM")
    def test_sending_i_frames_with_fcs_for_ertm(self):
        """
        Verify the IUT does include the FCS in I-frames.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()
        self.cert_l2cap.turn_on_fcs()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrameWithFcs(tx_seq=0, payload=b"abc"))

    @metadata(
        pts_test_id="L2CAP/OFS/BV-06-C",
        pts_test_name="Receiving I-Frames with FCS for ERTM")
    def test_aareceiving_i_frames_with_fcs_for_ertm(self):
        """
        Verify the IUT can handle I-frames that do contain the FCS.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()
        self.cert_l2cap.turn_on_fcs()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b"abc")
        assertThat(cert_channel).emits(
            L2capMatchers.IFrameWithFcs(tx_seq=0, payload=b"abc"))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-01-C", pts_test_name="Transmit I-frames")
    def test_transmit_i_frames(self):
        """
        Verify the IUT can send correctly formatted sequential I-frames with
        valid values for the enhanced control fields (SAR, F-bit, ReqSeq,
        TxSeq)
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b"abc"))

        cert_channel.send_i_frame(tx_seq=0, req_seq=1, payload=SAMPLE_PACKET)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=1, payload=b"abc"))

        cert_channel.send_i_frame(tx_seq=1, req_seq=2, payload=SAMPLE_PACKET)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(L2capMatchers.PartialData(b"abc"))

        cert_channel.send_i_frame(tx_seq=2, req_seq=3, payload=SAMPLE_PACKET)

    @metadata(pts_test_id="L2CAP/ERM/BV-02-C", pts_test_name="Receive I-Frames")
    def test_receive_i_frames(self):
        """
        Verify the IUT can receive in-sequence valid I-frames and deliver L2CAP
        SDUs to the Upper Tester
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        for i in range(3):
            cert_channel.send_i_frame(
                tx_seq=i, req_seq=0, payload=SAMPLE_PACKET)
            assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=i + 1))

        cert_channel.send_i_frame(
            tx_seq=3,
            req_seq=0,
            sar=SegmentationAndReassembly.START,
            payload=SAMPLE_PACKET)
        assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=4))

        cert_channel.send_i_frame(
            tx_seq=4,
            req_seq=0,
            sar=SegmentationAndReassembly.CONTINUATION,
            payload=SAMPLE_PACKET)
        assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=5))

        cert_channel.send_i_frame(
            tx_seq=5,
            req_seq=0,
            sar=SegmentationAndReassembly.END,
            payload=SAMPLE_PACKET)
        assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=6))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-03-C",
        pts_test_name="Acknowledging Received I-Frames")
    def test_acknowledging_received_i_frames(self):
        """
        Verify the IUT sends S-frame [RR] with the Poll bit not set to
        acknowledge data received from the Lower Tester
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        for i in range(3):
            cert_channel.send_i_frame(
                tx_seq=i, req_seq=0, payload=SAMPLE_PACKET)
            assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=i + 1))

        assertThat(cert_channel).emitsNone(
            L2capMatchers.SFrame(req_seq=4), timeout=timedelta(seconds=1))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-05-C",
        pts_test_name="Resume Transmitting I-Frames when an S-Frame [RR] "
        "is Received")
    def test_resume_transmitting_when_received_rr(self):
        """
        Verify the IUT will cease transmission of I-frames when the negotiated
        TxWindow is full. Verify the IUT will resume transmission of I-frames
        when an S-frame [RR] is received that acknowledges previously sent
        I-frames
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(tx_window_size=1)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        dut_channel.send(b'def')

        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'))
        assertThat(cert_channel).emitsNone(
            L2capMatchers.IFrame(tx_seq=1, payload=b'def'))

        cert_channel.send_s_frame(req_seq=1, f=Final.POLL_RESPONSE)
        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=1))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-06-C",
        pts_test_name="Resume Transmitting I-Frames when an I-Frame is "
        "Received")
    def test_resume_transmitting_when_acknowledge_previously_sent(self):
        """
        Verify the IUT will cease transmission of I-frames when the negotiated
        TxWindow is full. Verify the IUT will resume transmission of I-frames
        when an I-frame is received that acknowledges previously sent I-frames
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(tx_window_size=1)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        dut_channel.send(b'def')

        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'))
        # TODO: If 1 second is greater than their retransmit timeout, use a smaller timeout
        assertThat(cert_channel).emitsNone(
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc'),
            timeout=timedelta(seconds=1))

        cert_channel.send_i_frame(tx_seq=0, req_seq=1, payload=SAMPLE_PACKET)

        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=1, payload=b'def'))

        cert_channel.send_i_frame(tx_seq=1, req_seq=2, payload=SAMPLE_PACKET)

    @metadata(
        pts_test_id="L2CAP/ERM/BV-08-C",
        pts_test_name="Send S-Frame [RR] with Poll Bit Set")
    def test_transmit_s_frame_rr_with_poll_bit_set(self):
        """
        Verify the IUT sends an S-frame [RR] with the Poll bit set when its
        retransmission timer expires.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        # TODO: Always use their retransmission timeout value
        time.sleep(2)
        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(p=l2cap_packets.Poll.POLL))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-09-C",
        pts_test_name="Send S-Frame [RR] with Final Bit Set")
    def test_transmit_s_frame_rr_with_final_bit_set(self):
        """
        Verify the IUT responds with an S-frame [RR] with the Final bit set
        after receiving an S-frame [RR] with the Poll bit set
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        cert_channel.send_s_frame(req_seq=0, p=Poll.POLL)
        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(f=Final.POLL_RESPONSE))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-10-C",
        pts_test_name="Retransmit S-Frame [RR] with Final Bit Set")
    def test_retransmit_s_frame_rr_with_poll_bit_set(self):
        """
        Verify the IUT will retransmit the S-frame [RR] with the Poll bit set
        when the Monitor Timer expires
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(max_transmit=3)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)
        dut_channel.send(b'abc')

        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'))
        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(req_seq=0, p=Poll.POLL, f=Final.NOT_SET))
        cert_channel.send_s_frame(req_seq=1, f=Final.POLL_RESPONSE)

    @metadata(
        pts_test_id="L2CAP/ERM/BV-11-C",
        pts_test_name="S-Frame Transmissions Exceed MaxTransmit")
    def test_s_frame_transmissions_exceed_max_transmit(self):
        """
        Verify the IUT will close the channel when the Monitor Timer expires.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.reply_ertm_with_max_transmit_one()
        self.cert_l2cap.turn_on_ertm(tx_window_size=1, max_transmit=1)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')

        cert_channel.verify_disconnect_request()

    @metadata(
        pts_test_id="L2CAP/ERM/BV-12-C",
        pts_test_name="I-Frame Transmissions Exceed MaxTransmit")
    def test_i_frame_transmissions_exceed_max_transmit(self):
        """
        Verify the IUT will close the channel when it receives an S-frame [RR]
        with the final bit set that does not acknowledge the previous I-frame
        sent by the IUT
        """
        self._setup_link_from_cert()
        self.cert_l2cap.reply_ertm_with_max_transmit_one()
        self.cert_l2cap.turn_on_ertm(tx_window_size=1, max_transmit=1)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0),
            L2capMatchers.SFrame(p=Poll.POLL)).inOrder()

        cert_channel.send_s_frame(req_seq=0, f=Final.POLL_RESPONSE)
        cert_channel.verify_disconnect_request()

    @metadata(
        pts_test_id="L2CAP/ERM/BV-13-C",
        pts_test_name="Respond to S-Frame [REJ]")
    def test_respond_to_rej(self):
        """
        Verify the IUT retransmits I-frames starting from the sequence number
        specified in the S-frame [REJ]
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(tx_window_size=2, max_transmit=2)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc')).inOrder()

        cert_channel.send_s_frame(req_seq=0, s=SupervisoryFunction.REJECT)

        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc')).inOrder()

    @metadata(
        pts_test_id="L2CAP/ERM/BV-14-C",
        pts_test_name="Respond to S-Frame [SREJ] POLL Bit Set")
    def test_respond_to_srej_p_set(self):
        """
        Verify the IUT responds with the correct I-frame when sent an SREJ
        frame. Verify that the IUT processes the acknowledgment of previously
        unacknowledged I-frames
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(tx_window_size=3, max_transmit=2)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        for _ in range(4):
            dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=2, payload=b'abc')).inOrder()

        cert_channel.send_s_frame(
            req_seq=1, p=Poll.POLL, s=SupervisoryFunction.SELECT_REJECT)

        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(
                tx_seq=1, payload=b'abc', f=Final.POLL_RESPONSE),
            L2capMatchers.IFrame(tx_seq=3, payload=b'abc')).inOrder()

    @metadata(
        pts_test_id="L2CAP/ERM/BV-15-C",
        pts_test_name="Respond to S-Frame [SREJ] POLL Bit Clear")
    def test_respond_to_srej_p_clear(self):
        """
        Verify the IUT responds with the correct I-frame when sent an SREJ frame
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(tx_window_size=3, max_transmit=2)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        for _ in range(4):
            dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=2, payload=b'abc')).inOrder()

        cert_channel.send_s_frame(
            req_seq=1, s=SupervisoryFunction.SELECT_REJECT)
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc', f=Final.NOT_SET))
        cert_channel.send_s_frame(
            req_seq=3, s=SupervisoryFunction.RECEIVER_READY)
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=3, payload=b'abc', f=Final.NOT_SET))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-18-C",
        pts_test_name="Receive S-Frame [RR] Final Bit = 1")
    def test_receive_s_frame_rr_final_bit_set(self):
        """
        Verify the IUT will retransmit any previously sent I-frames
        unacknowledged by receipt of an S-Frame [RR] with the Final Bit set
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')

        # TODO: Always use their retransmission timeout value
        time.sleep(2)
        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(p=l2cap_packets.Poll.POLL))

        cert_channel.send_s_frame(req_seq=0, f=Final.POLL_RESPONSE)
        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=0))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-19-C",
        pts_test_name="Receive I-Frame Final Bit = 1")
    def test_receive_i_frame_final_bit_set(self):
        """
        Verify the IUT will retransmit any previously sent I-frames
        unacknowledged by receipt of an I-frame with the final bit set
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')

        # TODO: Always use their retransmission timeout value
        time.sleep(2)
        assertThat(cert_channel).emits(L2capMatchers.SFrame(p=Poll.POLL))

        cert_channel.send_i_frame(
            tx_seq=0, req_seq=0, f=Final.POLL_RESPONSE, payload=SAMPLE_PACKET)

        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=0))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-20-C",
        pts_test_name="Enter Remote Busy Condition")
    def test_receive_rnr(self):
        """
        Verify the IUT will not retransmit any I-frames when it receives a
        remote busy indication from the Lower Tester (S-frame [RNR])
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')

        # TODO: Always use their retransmission timeout value
        time.sleep(2)
        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(p=l2cap_packets.Poll.POLL))

        cert_channel.send_s_frame(
            req_seq=0,
            s=SupervisoryFunction.RECEIVER_NOT_READY,
            f=Final.POLL_RESPONSE)
        assertThat(cert_channel).emitsNone(L2capMatchers.IFrame(tx_seq=0))

    @metadata(
        pts_test_id="L2CAP/ERM/BV-23-C",
        pts_test_name="Transmit I-Frames using SAR")
    def test_transmit_i_frames_using_sar(self):
        """
        Verify the IUT can send correctly formatted sequential I-frames with
        valid values for the enhanced control fields (SAR, F-bit, ReqSeq,
        TxSeq) when performing SAR.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.reply_ertm_with_specified_mps(11)
        self.cert_l2cap.turn_on_ertm(tx_window_size=3, max_transmit=2, mps=11)

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abcabcabc')
        # First IFrame should contain SDU size after control field
        assertThat(cert_channel).emits(
            L2capMatchers.IFrameStart(tx_seq=0, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=1, payload=b'abc'),
            L2capMatchers.IFrame(tx_seq=2, payload=b'abc')).inOrder()

        cert_channel.send_s_frame(
            req_seq=3, s=SupervisoryFunction.RECEIVER_READY)

        dut_channel.send(b'defdefdef')
        # First IFrame should contain SDU size after control field
        assertThat(cert_channel).emits(
            L2capMatchers.IFrameStart(tx_seq=3, payload=b'def'),
            L2capMatchers.IFrame(tx_seq=4, payload=b'def'),
            L2capMatchers.IFrame(tx_seq=5, payload=b'def')).inOrder()

    @metadata(
        pts_test_id="L2CAP/ERM/BI-01-C",
        pts_test_name="S-Frame [REJ] Lost or Corrupted")
    def test_sent_rej_lost(self):
        """
        Verify the IUT can handle receipt of an S-=frame [RR] Poll = 1 if the
        S-frame [REJ] sent from the IUT is lost
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm(tx_window_size=5)
        ertm_tx_window_size = 5

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x41, mode=RetransmissionFlowControlMode.ERTM)

        cert_channel.send_i_frame(tx_seq=0, req_seq=0, payload=SAMPLE_PACKET)
        assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=1))

        cert_channel.send_i_frame(
            tx_seq=ertm_tx_window_size - 1, req_seq=0, payload=SAMPLE_PACKET)
        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(s=SupervisoryFunction.REJECT))

        cert_channel.send_s_frame(req_seq=0, p=Poll.POLL)

        assertThat(cert_channel).emits(
            L2capMatchers.SFrame(
                req_seq=1, f=l2cap_packets.Final.POLL_RESPONSE))
        for i in range(1, ertm_tx_window_size):
            cert_channel.send_i_frame(
                tx_seq=i, req_seq=0, payload=SAMPLE_PACKET)
            assertThat(cert_channel).emits(L2capMatchers.SFrame(req_seq=i + 1))

    @metadata(
        pts_test_id="L2CAP/ERM/BI-03-C",
        pts_test_name="Handle Duplicate S-Frame [SREJ]")
    def test_handle_duplicate_srej(self):
        """
        Verify the IUT will only retransmit the requested I-frame once after
        receiving a duplicate SREJ
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0),
            L2capMatchers.IFrame(tx_seq=1),
            L2capMatchers.SFrame(p=Poll.POLL)).inOrder()

        cert_channel.send_s_frame(
            req_seq=0, s=SupervisoryFunction.SELECT_REJECT)
        assertThat(cert_channel).emitsNone(timeout=timedelta(seconds=0.5))

        cert_channel.send_s_frame(
            req_seq=0,
            s=SupervisoryFunction.SELECT_REJECT,
            f=Final.POLL_RESPONSE)
        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=0))

    @metadata(
        pts_test_id="L2CAP/ERM/BI-04-C",
        pts_test_name="Handle Receipt of S-Frame [REJ] and S-Frame "
        "[RR, F=1] that Both Require Retransmission of the "
        "Same I-Frames")
    def test_handle_receipt_rej_and_rr_with_f_set(self):
        """
        Verify the IUT will only retransmit the requested I-frames once after
        receiving an S-frame [REJ] followed by an S-frame [RR] with the Final
        bit set that indicates the same I-frames should be retransmitted
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0),
            L2capMatchers.IFrame(tx_seq=1),
            L2capMatchers.SFrame(p=l2cap_packets.Poll.POLL)).inOrder()

        cert_channel.send_s_frame(req_seq=0, s=SupervisoryFunction.REJECT)
        assertThat(cert_channel).emitsNone(timeout=timedelta(seconds=0.5))

        # Send RR with F set
        cert_channel.send_s_frame(
            req_seq=0, s=SupervisoryFunction.REJECT, f=Final.POLL_RESPONSE)
        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=0))
        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=1))

    @metadata(
        pts_test_id="L2CAP/ERM/BI-05-C",
        pts_test_name="Handle receipt of S-Frame [REJ] and I-Frame [F=1] "
        "that Both Require Retransmission of the Same "
        "I-Frames")
    def test_handle_rej_and_i_frame_with_f_set(self):
        """
        Verify the IUT will only retransmit the requested I-frames once after
        receiving an S-frame [REJ] followed by an I-frame with the Final bit
        set that indicates the same I-frames should be retransmitted
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        (dut_channel, cert_channel) = self._open_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        dut_channel.send(b'abc')
        dut_channel.send(b'abc')
        assertThat(cert_channel).emits(
            L2capMatchers.IFrame(tx_seq=0),
            L2capMatchers.IFrame(tx_seq=1),
            L2capMatchers.SFrame(p=l2cap_packets.Poll.POLL)).inOrder()

        # Send SREJ with F not set
        cert_channel.send_s_frame(
            req_seq=0, s=SupervisoryFunction.SELECT_REJECT)
        assertThat(cert_channel).emitsNone(timeout=timedelta(seconds=0.5))

        cert_channel.send_i_frame(
            tx_seq=0, req_seq=0, f=Final.POLL_RESPONSE, payload=SAMPLE_PACKET)

        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=0))
        assertThat(cert_channel).emits(L2capMatchers.IFrame(tx_seq=1))

    @metadata(
        pts_test_id="L2CAP/CMC/BV-01-C",
        pts_test_name="IUT Initiated Configuration of Enhanced "
        "Retransmission Mode")
    def test_initiated_configuration_request_ertm(self):
        """
        Verify the IUT can send a Configuration Request command containing the
        F&EC option that specifies Enhanced Retransmission Mode
        """
        self._setup_link_from_cert()
        self.cert_l2cap.turn_on_ertm()

        self._open_unvalidated_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)

        # TODO: Fix this test. It doesn't work so far with PDL struct

        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationRequest())
        asserts.skip("Struct not working")

    @metadata(
        pts_test_id="L2CAP/CMC/BV-02-C",
        pts_test_name="Lower Tester Initiated Configuration of Enhanced "
        "Retransmission Mode")
    def test_respond_configuration_request_ertm(self):
        """
        Verify the IUT can accept a Configuration Request from the Lower Tester
        containing an F&EC option that specifies Enhanced Retransmission Mode
        """
        asserts.skip("ConfigurationResponseView Not working")
        self._setup_link_from_cert()
        psm = 1
        scid = 0x0101
        self.retransmission_mode = RetransmissionFlowControlMode.ERTM
        self.dut.l2cap.SetDynamicChannel(
            l2cap_facade_pb2.SetEnableDynamicChannelRequest(
                psm=psm, retransmission_mode=self.retransmission_mode))

        open_channel = l2cap_packets.ConnectionRequestBuilder(1, psm, scid)
        open_channel_l2cap = l2cap_packets.BasicFrameBuilder(1, open_channel)
        self.cert_send_b_frame(open_channel_l2cap)

        # TODO: Verify that the type should be ERTM
        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationResponse())

    @metadata(
        pts_test_id="L2CAP/CMC/BV-12-C",
        pts_test_name="ERTM Not Supported by Lower Tester for Mandatory "
        "ERTM channel")
    def test_respond_not_support_ertm_when_using_mandatory_ertm(self):
        """
        The IUT is initiating connection of an L2CAP channel that mandates use
        of ERTM. Verify the IUT will not attempt to configure the connection to
        ERTM if the Lower Tester has not indicated support for ERTM in the
        Information Response [Extended Features]
        """
        self._setup_link_from_cert()
        dut_channel_future = self.dut_l2cap.connect_dynamic_channel_to_cert(
            psm=0x33, mode=RetransmissionFlowControlMode.ERTM)
        assertThat(self.cert_l2cap.get_control_channel()).emitsNone(
            L2capMatchers.ConnectionRequest(0x33))

    @metadata(
        pts_test_id="L2CAP/CMC/BI-01-C",
        pts_test_name="Failed Configuration of Enhanced Retransmission "
        "Mode when use of the Mode is Mandatory]")
    def test_config_respond_basic_mode_when_using_mandatory_ertm(self):
        """
        When creating a connection for a PSM that mandates the use of ERTM
        verify the IUT can handle receipt (close the channel in accordance with
        the specification) of a Configure Response indicating the peer L2CAP
        entity doesn’t wish to use Enhanced Retransmission Mode (Configure
        Response Result = Reject Unacceptable Parameters)
        """
        self._setup_link_from_cert()
        self.cert_l2cap.reply_with_basic_mode()
        (dut_channel, cert_channel) = self._open_unvalidated_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)
        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationRequest())
        cert_channel.verify_disconnect_request()

    @metadata(
        pts_test_id="L2CAP/CMC/BI-02-C",
        pts_test_name="Configuration Mode mismatch when use of Enhanced "
        "Retransmission Mode is Mandatory")
    def test_config_request_basic_mode_when_using_mandatory_ertm(self):
        """
        When creating a connection for a PSM that mandates the use of ERTM,
        verify the IUT will close the channel if the Lower Tester attempts to
        configure Basic Mode.
        """
        self._setup_link_from_cert()
        self.cert_l2cap.reply_with_nothing()
        self.cert_l2cap.config_with_basic_mode()
        (dut_channel, cert_channel) = self._open_unvalidated_channel(
            scid=0x41, psm=0x33, mode=RetransmissionFlowControlMode.ERTM)
        assertThat(self.cert_l2cap.get_control_channel()).emits(
            L2capMatchers.ConfigurationRequest())
        cert_channel.verify_disconnect_request()
