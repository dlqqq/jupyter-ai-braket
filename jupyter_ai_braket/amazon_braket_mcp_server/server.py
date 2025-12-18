# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions
# and limitations under the License.

"""awslabs braket MCP Server implementation."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from qiskit import QuantumCircuit as QiskitCircuit, qasm3

from .models import (
    QuantumCircuit,
    Gate,
    TaskResult,
    TaskStatus,
    DeviceInfo,
    DeviceType,
)
from .braket_service import BraketService
from loguru import logger
from mcp.server.fastmcp import FastMCP


# Remove all default handlers then add our own
logger.remove()
logger.add(sys.stderr, level='INFO')

# Initialize FastMCP
mcp = FastMCP(
    'awslabs.braket-mcp-server',
    instructions='This server provides the ability to create, run, and analyze quantum circuits using Qiskit with Amazon Braket.',
    dependencies=['pydantic', 'loguru', 'boto3', 'amazon-braket-sdk', 'qiskit', 'qiskit-braket-provider'],
)

# Global variable to hold the braket service instance
_braket_service = None


def get_braket_service():
    """Lazily initialize the Braket service connection.

    This function ensures the service is only initialized when needed,
    not at import time, which helps with testing.

    Returns:
        BraketService: The initialized Braket service instance
    """
    global _braket_service
    if _braket_service is None:
        region = os.environ.get('AWS_REGION', None)
        workspace_dir = os.environ.get('BRAKET_WORKSPACE_DIR', os.getcwd())
        logger.info(f'AWS_REGION: {region}')
        logger.info(f'BRAKET_WORKSPACE_DIR: {workspace_dir}')
        _braket_service = BraketService(region_name=region, workspace_dir=workspace_dir)

    return _braket_service


# Add default device ARN support
def get_default_device_arn():
    """Get the default device ARN from environment or use SV1 simulator."""
    arn = os.environ.get('BRAKET_DEFAULT_DEVICE_ARN', '').strip()
    if not arn:  # Handle empty string or None
        return 'arn:aws:braket:::device/quantum-simulator/amazon/sv1'
    return arn


@mcp.resource(uri='amazon-braket://devices', name='QuantumDevices', mime_type='application/json')
def get_devices_resource() -> List[DeviceInfo]:
    """Get the list of available quantum devices."""
    return get_braket_service().list_devices()


@mcp.tool(name='create_quantum_circuit')
def create_quantum_circuit(qasm_program: str, filename: Optional[str] = None) -> Dict[str, Any]:
    """Create a quantum circuit from an OpenQASM 3.0 program string.

    Args:
        qasm_program: String containing the OpenQASM 3.0 program
        filename: Optional filename for the .qasm file. If provided, the circuit is saved to this file.
                  If not provided, the circuit is only verified and visualized without saving.

    Returns:
        Dictionary containing the verification status, circuit diagram, and file path (if saved)
    """
    try:
        # Verify the QASM 3.0 program by loading it with qiskit
        logger.info("Verifying OpenQASM 3.0 program...")
        circuit = qasm3.loads(qasm_program)
        logger.info(f"Successfully verified circuit with {circuit.num_qubits} qubits and {len(circuit.data)} operations")

        # Generate ASCII rendering of the circuit
        logger.info("Generating circuit ASCII visualization...")
        ascii_diagram = circuit.draw(output='text')

        # Prepare base response
        response = {
            'success': True,
            'num_qubits': circuit.num_qubits,
            'num_operations': len(circuit.data),
            'circuit_diagram': str(ascii_diagram),
        }

        # Save to file if filename is provided
        if filename:
            # Use current working directory
            workspace_dir = Path(os.getcwd())

            # Ensure the workspace directory exists
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # Construct the full file path
            file_path = workspace_dir / filename

            # Save the QASM 3.0 code to the file
            logger.info(f"Saving QASM 3.0 program to {file_path}...")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(qasm_program)

            logger.info(f"Successfully saved QASM 3.0 program to {file_path}")
            response['file_path'] = str(file_path)
            response['message'] = f'Circuit verified and saved to {file_path}'
        else:
            logger.info("No filename provided, skipping file save")
            response['message'] = 'Circuit verified successfully (not saved to file)'

        return response
    except Exception as e:
        logger.exception(f"Error creating quantum circuit: {str(e)}")
        return {'error': str(e), 'success': False}


# @mcp.tool(name='run_quantum_task')
# def run_quantum_task(
#     circuit: Dict[str, Any],
#     device_arn: Optional[str] = None,
#     shots: int = 1000,
#     s3_bucket: Optional[str] = None,
#     s3_prefix: Optional[str] = None,
# ) -> Dict[str, Any]:
#     """Run a quantum circuit on an Amazon Braket device.
    
#     Args:
#         circuit: Quantum circuit definition
#         device_arn: ARN of the device to run the task on (optional, uses default if not provided)
#         shots: Number of shots to run
#         s3_bucket: S3 bucket for storing results (optional)
#         s3_prefix: S3 prefix for storing results (optional)
    
#     Returns:
#         Dictionary containing the task ID and status
#     """
#     try:
#         # Use default device ARN if none provided
#         if device_arn is None:
#             device_arn = get_default_device_arn()
#             logger.info(f"Using default device ARN: {device_arn}")
        
#         # Convert the circuit dictionary to a QuantumCircuit object
#         gate_objects = []
#         for gate_dict in circuit.get('gates', []):
#             gate = Gate(
#                 name=gate_dict.get('name'),
#                 qubits=gate_dict.get('qubits', []),
#                 params=gate_dict.get('params'),
#             )
#             gate_objects.append(gate)
        
#         circuit_def = QuantumCircuit(
#             num_qubits=circuit.get('num_qubits'),
#             gates=gate_objects,
#             metadata=circuit.get('metadata'),
#         )
        
#         # Run the quantum task
#         task_id = get_braket_service().run_quantum_task(
#             circuit=circuit_def,
#             device_arn=device_arn,
#             shots=shots,
#             s3_bucket=s3_bucket,
#             s3_prefix=s3_prefix,
#         )
        
#         return {
#             'task_id': task_id,
#             'status': 'CREATED',
#             'device_arn': device_arn,
#             'shots': shots,
#         }
#     except Exception as e:
#         logger.exception(f"Error running quantum task: {str(e)}")
#         return {'error': str(e)}


@mcp.tool(name='get_task_result')
def get_task_result(task_id: str) -> Dict[str, Any]:
    """Get the result of a quantum task.
    
    Args:
        task_id: ID of the quantum task
    
    Returns:
        Dictionary containing the task result
    """
    try:
        # Get the task result
        result = get_braket_service().get_task_result(task_id)
        
        # Return the result as a dictionary
        return result.model_dump()
    except Exception as e:
        logger.exception(f"Error getting task result: {str(e)}")
        return {'error': str(e)}


@mcp.tool(name='list_devices')
def list_devices() -> List[Dict[str, Any]]:
    """List available quantum devices.
    
    Returns:
        List of available quantum devices
    """
    try:
        # Get the list of devices
        devices = get_braket_service().list_devices()
        
        # Convert to dictionaries
        return [device.model_dump() for device in devices]
    except Exception as e:
        logger.exception(f"Error listing devices: {str(e)}")
        return [{'error': str(e)}]


@mcp.tool(name='get_device_info')
def get_device_info(device_arn: str) -> Dict[str, Any]:
    """Get information about a specific quantum device.
    
    Args:
        device_arn: ARN of the device
    
    Returns:
        Dictionary containing device information
    """
    try:
        # Get the device information
        device_info = get_braket_service().get_device_info(device_arn)
        
        # Return the device info as a dictionary
        return device_info.model_dump()
    except Exception as e:
        logger.exception(f"Error getting device info: {str(e)}")
        return {'error': str(e)}


@mcp.tool(name='cancel_quantum_task')
def cancel_quantum_task(task_id: str) -> Dict[str, Any]:
    """Cancel a quantum task.
    
    Args:
        task_id: ID of the quantum task to cancel
    
    Returns:
        Dictionary indicating success or failure
    """
    try:
        # Cancel the task
        success = get_braket_service().cancel_quantum_task(task_id)
        
        return {
            'task_id': task_id,
            'cancelled': success,
        }
    except Exception as e:
        logger.exception(f"Error cancelling quantum task: {str(e)}")
        return {'error': str(e)}


@mcp.tool(name='search_quantum_tasks')
def search_quantum_tasks(
    device_arn: Optional[str] = None,
    state: Optional[str] = None,
    max_results: int = 10,
    days_ago: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Search for quantum tasks.
    
    Args:
        device_arn: Filter by device ARN
        state: Filter by task state
        max_results: Maximum number of results to return
        days_ago: Filter by creation time (days ago)
    
    Returns:
        List of quantum tasks
    """
    try:
        # Calculate the created_after date if days_ago is provided
        created_after = None
        if days_ago is not None:
            created_after = datetime.now() - timedelta(days=days_ago)
        
        # Search for tasks
        tasks = get_braket_service().search_quantum_tasks(
            device_arn=device_arn,
            state=state,
            max_results=max_results,
            created_after=created_after,
        )
        
        return tasks
    except Exception as e:
        logger.exception(f"Error searching quantum tasks: {str(e)}")
        return [{'error': str(e)}]


@mcp.tool(name='create_bell_pair_circuit')
def create_bell_pair_circuit(filename: Optional[str] = None) -> Dict[str, Any]:
    """Create a Bell pair circuit (entangled qubits).

    Args:
        filename: Optional filename for the .qasm file. If provided, the circuit is saved to this file.
                  If not provided, the circuit is only verified and visualized without saving.

    Returns:
        Dictionary containing the verification status, ASCII circuit diagram, and file path (if saved)
    """
    try:
        # Create Bell pair circuit using Qiskit
        circuit = QiskitCircuit(2)
        circuit.h(0)  # Hadamard on qubit 0
        circuit.cx(0, 1)  # CNOT with control=0, target=1
        circuit.measure_all()  # Add measurements

        # Convert to QASM 3.0
        qasm_program = qasm3.dumps(circuit)

        # Call create_quantum_circuit to verify and save
        return create_quantum_circuit(qasm_program, filename)
    except Exception as e:
        logger.exception(f"Error creating Bell pair circuit: {str(e)}")
        return {'error': str(e), 'success': False}


@mcp.tool(name='create_ghz_circuit')
def create_ghz_circuit(filename: Optional[str] = None, num_qubits: int = 3) -> Dict[str, Any]:
    """Create a GHZ state circuit.

    Args:
        filename: Optional filename for the .qasm file. If provided, the circuit is saved to this file.
                  If not provided, the circuit is only verified and visualized without saving.
        num_qubits: Number of qubits in the circuit (default: 3)

    Returns:
        Dictionary containing the verification status, ASCII circuit diagram, and file path (if saved)
    """
    try:
        # Create GHZ circuit using Qiskit
        circuit = QiskitCircuit(num_qubits)
        circuit.h(0)  # Hadamard on qubit 0
        for i in range(num_qubits - 1):
            circuit.cx(i, i + 1)  # Chain of CNOT gates
        circuit.measure_all()  # Add measurements

        # Convert to QASM 3.0
        qasm_program = qasm3.dumps(circuit)

        # Call create_quantum_circuit to verify and save
        return create_quantum_circuit(qasm_program, filename)
    except Exception as e:
        logger.exception(f"Error creating GHZ circuit: {str(e)}")
        return {'error': str(e), 'success': False}


@mcp.tool(name='create_qft_circuit')
def create_qft_circuit(filename: Optional[str] = None, num_qubits: int = 3) -> Dict[str, Any]:
    """Create a Quantum Fourier Transform circuit.

    Args:
        filename: Optional filename for the .qasm file. If provided, the circuit is saved to this file.
                  If not provided, the circuit is only verified and visualized without saving.
        num_qubits: Number of qubits in the circuit (default: 3)

    Returns:
        Dictionary containing the verification status, ASCII circuit diagram, and file path (if saved)
    """
    try:
        # Create QFT circuit using Qiskit
        circuit = QiskitCircuit(num_qubits)

        # Implement QFT algorithm
        import math
        for i in range(num_qubits):
            # Apply Hadamard gate
            circuit.h(i)
            # Apply controlled-phase rotations
            for j in range(i + 1, num_qubits):
                angle = 2 * math.pi / (2 ** (j - i + 1))
                circuit.cp(angle, j, i)

        # Reverse qubit order with SWAP gates
        for i in range(num_qubits // 2):
            circuit.swap(i, num_qubits - i - 1)

        circuit.measure_all()  # Add measurements

        # Convert to QASM 3.0
        qasm_program = qasm3.dumps(circuit)

        # Call create_quantum_circuit to verify and save
        return create_quantum_circuit(qasm_program, filename)
    except Exception as e:
        logger.exception(f"Error creating QFT circuit: {str(e)}")
        return {'error': str(e), 'success': False}


# @mcp.tool(name='visualize_circuit')
# def visualize_circuit(circuit: Dict[str, Any]) -> Dict[str, Any]:
#     """Visualize a quantum circuit.
    
#     Args:
#         circuit: Quantum circuit definition
    
#     Returns:
#         Dictionary containing the visualization
#     """
#     try:
#         # Convert the circuit dictionary to a QuantumCircuit object
#         gate_objects = []
#         for gate_dict in circuit.get('gates', []):
#             gate = Gate(
#                 name=gate_dict.get('name'),
#                 qubits=gate_dict.get('qubits', []),
#                 params=gate_dict.get('params'),
#             )
#             gate_objects.append(gate)
        
#         circuit_def = QuantumCircuit(
#             num_qubits=circuit.get('num_qubits'),
#             gates=gate_objects,
#             metadata=circuit.get('metadata'),
#         )
        
#         # Visualize the circuit
#         circuit_image = get_braket_service().visualize_circuit(circuit_def)
        
#         return {
#             'visualization': circuit_image,
#         }
#     except Exception as e:
#         logger.exception(f"Error visualizing circuit: {str(e)}")
#         return {'error': str(e)}


@mcp.tool(name='visualize_results')
def visualize_results(result: Dict[str, Any]) -> Dict[str, Any]:
    """Visualize the results of a quantum task.
    
    Args:
        result: Result of the quantum task
    
    Returns:
        Dictionary containing the visualization
    """
    try:
        # Convert the result dictionary to a TaskResult object
        task_result = TaskResult(
            task_id=result.get('task_id'),
            status=result.get('status'),
            measurements=result.get('measurements'),
            counts=result.get('counts'),
            device=result.get('device'),
            shots=result.get('shots'),
            execution_time=result.get('execution_time'),
            metadata=result.get('metadata'),
        )
        
        # Create visualization
        response = get_braket_service().create_results_visualization(task_result)
        
        return response
    except Exception as e:
        logger.exception(f"Error visualizing results: {str(e)}")
        return {'error': str(e)}


@mcp.tool(name='describe_visualization')
def describe_visualization(visualization_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert visualization data into human-readable descriptions.
    
    Args:
        visualization_data: Visualization data from circuit or results
    
    Returns:
        Dictionary containing human-readable descriptions
    """
    try:
        # Check if this is circuit or results data
        if 'circuit_def' in visualization_data:
            # This is circuit visualization data
            circuit_dict = visualization_data['circuit_def']
            
            # Convert to QuantumCircuit object
            gate_objects = []
            for gate_dict in circuit_dict.get('gates', []):
                gate = Gate(
                    name=gate_dict.get('name'),
                    qubits=gate_dict.get('qubits', []),
                    params=gate_dict.get('params'),
                )
                gate_objects.append(gate)
            
            circuit_def = QuantumCircuit(
                num_qubits=circuit_dict.get('num_qubits'),
                gates=gate_objects,
                metadata=circuit_dict.get('metadata'),
            )
            
            # Generate description
            description = get_braket_service().describe_circuit(circuit_def)
            return {
                'type': 'circuit_description',
                'description': description
            }
            
        elif 'result' in visualization_data:
            # This is results visualization data
            result_dict = visualization_data['result']
            
            # Convert to TaskResult object
            task_result = TaskResult(
                task_id=result_dict.get('task_id'),
                status=result_dict.get('status'),
                measurements=result_dict.get('measurements'),
                counts=result_dict.get('counts'),
                device=result_dict.get('device'),
                shots=result_dict.get('shots'),
                execution_time=result_dict.get('execution_time'),
                metadata=result_dict.get('metadata'),
            )
            
            # Generate description
            description = get_braket_service().describe_results(task_result)
            return {
                'type': 'results_description',
                'description': description
            }
        else:
            return {
                'error': 'Unknown visualization data format. Expected circuit_def or result fields.'
            }
            
    except Exception as e:
        logger.exception(f"Error describing visualization: {str(e)}")
        return {'error': str(e)}


def main():
    """Run the MCP server with CLI argument support."""
    mcp.run()


if __name__ == '__main__':
    main()
