"""All the Kernels: all your kernels in one kernel.

Like magic!
"""

import os
import sys

from tornado import gen
from tornado.ioloop import IOLoop

import zmq
from zmq.eventloop import ioloop
ioloop.install()
from zmq.eventloop.future import Context

from traitlets import Dict

from jupyter_client import KernelManager
from ipykernel.kernelbase import Kernel
from ipykernel.kernelapp import IPKernelApp


banner = """\
All The Kernels: A single Jupyter kernel that multiplexes all 

For instance, use

    >python2
    def foo():
        ...

Will run the cell in a Python 2 kernel

    >julia-0.4
    
Will run in Julia 0.4, etc.
"""

__version__ = '0.0.1'

class KernelProxy(object):
    """A proxy for a single kernel
    
    Hooks up relay of messages on the shell channel.
    """
    def __init__(self, manager, shell_upstream):
        self.manager = manager
        self.shell = self.manager.connect_shell()
        self.shell_upstream = shell_upstream
        self.iopub_url = self.manager._make_url('iopub')
        IOLoop.current().add_callback(self.relay_shell)
    
    @gen.coroutine
    def relay_shell(self):
        """Coroutine for relaying any shell replies"""
        while True:
            msg = yield self.shell.recv_multipart()
            self.shell_upstream.send_multipart(msg)


class AllTheKernels(Kernel):
    """Kernel class for proxying ALL THE KERNELS YOU HAVE"""
    implementation = 'AllTheKernels'
    implementation_version = '0.1'
    language_info = {
        'name': 'all-of-them',
        'mimetype': 'text/plain',
    }
    banner = banner
    
    kernels = Dict()
    default_kernel = 'python%i' % (sys.version_info[0])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.future_context = ctx = Context()
        self.iosub = ctx.socket(zmq.SUB)
        self.iosub.subscribe = b''
        self.shell_stream = self.shell_streams[0]
    
    def start(self):
        super().start()
        loop = IOLoop.current()
        loop.add_callback(self.relay_iopub_messages)
    
    @gen.coroutine
    def relay_iopub_messages(self):
        """Coroutine for relaying IOPub messages from all of our kernels"""
        while True:
            msg = yield self.iosub.recv_multipart()
            self.iopub_socket.send_multipart(msg)

    def start_kernel(self, name):
        """Start a new kernel"""
        base, ext = os.path.splitext(self.parent.connection_file)
        cf = '{base}-{name}{ext}'.format(
            base=base,
            name=name,
            ext=ext,
        )
        manager = KernelManager(
            kernel_name=name,
            session=self.session,
            context=self.future_context,
            connection_file=cf,
        )
        manager.start_kernel()
        self.kernels[name] = kernel = KernelProxy(
            manager=manager,
            shell_upstream=self.shell_stream)
        self.iosub.connect(kernel.iopub_url)
        return self.kernels[name]
    
    def get_kernel(self, name):
        """Get a kernel, start it if it doesn't exist"""
        if name not in self.kernels:
            self.start_kernel(name)
        return self.kernels[name]
    
    def split_cell(self, cell):
        """Return the kernel name and remaining cell contents
        
        If no kernel name is specified, use the default kernel.
        """
        if not cell.startswith('>'):
            # no kernel magic, use default kernel
            return self.default_kernel, cell
        split = cell.split('\n', 1)
        if len(split) == 2:
            first_line, cell = split
        else:
            first_line = cell
            cell = ''
        kernel_name = first_line[1:].strip()
        return kernel_name, cell
    
    def _publish_status(self, status):
        """Disabling publishing status messages
        
        Status messages will be relayed from the actual kernels.
        """
        return
    
    def relay_to_kernel(self, stream, ident, parent):
        """Relay a message to a kernel
        
        Gets the `>kernel` line off of the cell,
        finds the kernel (starts it if necessary),
        then relays the request.
        """
        content = parent['content']
        cell = content['code']
        kernel_name, cell = self.split_cell(cell)
        content['code'] = cell
        kernel = self.get_kernel(kernel_name)
        self.session.send(kernel.shell, parent, ident=ident)
    
    execute_request = relay_to_kernel
    inspect_request = relay_to_kernel
    complete_request = relay_to_kernel


class AllTheKernelsApp(IPKernelApp):

    kernel_class = AllTheKernels

    def _log_level_default(self):
        return 10

    def init_io(self):
        # disable IO capture
        return

main = AllTheKernelsApp.launch_instance

if __name__ == '__main__':
    main()
