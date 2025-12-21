from typing import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.namespace import Namespace
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.net.traffic_generator import TcpServer, VMTcpClient, is_tcp_connection
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.udn import UDN_BINDING_PASST
from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.vm_factory import udn_vm
from tests.utils import register_passt_and_wait_for_sync
from utilities.virt import migrate_vm_and_verify

IP_ADDRESS = "ipAddress"
SERVER_PORT = 5201



@pytest.fixture(scope="class")
def passt_enabled_in_hco(
    admin_client: DynamicClient,
    hco_namespace: Namespace,
    hyperconverged_resource_scope_class: HyperConverged,
) -> Generator[None, None, None]:
    with register_passt_and_wait_for_sync(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_class,
    ):
        yield


@pytest.fixture(scope="class")
def passt_vm_a(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine, None, None]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vma-passt",
        client=admin_client,
        template_labels=dict((udn_affinity_label,)),
        binding=UDN_BINDING_PASST,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def passt_vm_b(
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
    udn_affinity_label: tuple[str, str],
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine, None, None]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="vmb-passt",
        client=admin_client,
        template_labels=dict((udn_affinity_label,)),
        binding=UDN_BINDING_PASST,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def server_passt(passt_vm_b: BaseVirtualMachine) -> Generator[TcpServer, None, None]:
    with TcpServer(vm=passt_vm_b, port=SERVER_PORT) as server:
        yield server


@pytest.fixture(scope="class")
def client_passt(
    passt_vm_a: BaseVirtualMachine,
    passt_vm_b: BaseVirtualMachine,
) -> Generator[VMTcpClient, None, None]:
    with TcpClient(
        vm=passt_vm_a,
        server_ip=lookup_iface_status(vm=passt_vm_b, iface_name=lookup_primary_network(vm=passt_vm_b).name)[IP_ADDRESS],
        server_port=SERVER_PORT,
    ) as client:
        yield client


@pytest.mark.ipv4
@pytest.mark.usefixtures()
class TestPrimaryUdnPasst:
    @pytest.mark.polarion("CNV-12427")
    @pytest.mark.single_nic
    def test_passt_connectivity_is_preserved_during_client_live_migration(self, passt_enabled_in_hco, server_passt, client_passt):
        migrate_vm_and_verify(vm=client_passt.vm)
        assert is_tcp_connection(server=server_passt, client=client_passt)

    @pytest.mark.polarion("CNV-12428")
    @pytest.mark.single_nic
    def test_passt_connectivity_is_preserved_during_server_live_migration(self, passt_enabled_in_hco, server_passt, client_passt):
        migrate_vm_and_verify(vm=server_passt.vm)
        assert is_tcp_connection(server=server_passt, client=client_passt)
