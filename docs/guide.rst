.. comment -*- mode: rst -*-

Concepts
========

``Sxsuite`` package provides a framework for building messaging application 
for class of protocols often used in financial applications. Typical for these 
protocols is that session concept spans over multiple network connections. 
There is typically session initiator (client or buyside ) and acceptor (server or
sell-side). Client opens network connection with login that server needs to accepts 
before actual messaging starts. Usually messages are numbers and client and/or server
can request resending of messages.

Prime example of these protocols is the FIX protocol.

Classes
*******

``Session`` holds the actual session data. This includes the state of the session (IDLE,
LOGIN, INSESSION or STOPPED), current sequence numbers and all configuration items.

IDLE
	Session has no active open channel to other side

LOGIN
	Channel has been opened and session login is in process

INSESSION
	Normal operation

STOPPED
	Session is not active

Session object links to ``Transport`` object that is the actual network connection
or other communication channel. 

Session protocol is implemented in a subclass of ``Protocol`` class. This class
internal message formats to wire format and vice versa. This class handles protocol
spesific administrative messages like heartbeat, resend request and others. All 
actual data messages are passed forward to session object for passing up for
upper layers.

Session object are stackable. The ``Session`` object holding the actual live 
communication channel is the bottom of the stack. Topmost object of the stack is an
instance of ``Application`` class. All object between are instances of ``Filter``
class.


Message flow
************

Incoming message flow
---------------------

t.handle_read()
	Event loop runner excutes for transports that have data available for reading

s.event_readable(transport)
	Called by ``t.handle_read`` to indicate session of incoming data
	Reads data from live transport and passes it forward.

s.recv(data)
	Called by ``s.event_readable`` to handle data coming from live transport. Or
	alternatively by lower level session object to pass incoming message forward.
	At lowest session level this method implements the basic session state
	handling. If session state is LOGIN protocol spesific login handling is
	initiated. Successfull login changes session to INSESSION state

p.received(data)
	Called by ``s.recv`` to handle received and validated protocol message.
	If message is protocol payload data message then it is passed forward.

s.received(data)
	Incoming data message from ``p.received``. This will call ``upstream`` method 
	of its upstream object to push data forward.

s.upstream(data)
	Entry point for downstream modules to push data to upstream module. If module
	is bottom module (like ``Session``) calling ``upstream`` will raise
	``ConfigError`` exception with ``S_ENOUPLINK`` error.

p.validate(data)
	Validates message and converts to internal presentation from wire format.
	Called by ``s.recv`` to validate message.
	
p.login_auth(data)
	Called by ``s.recv`` to handle messages in LOGIN state.	


Outgoing message flow
---------------------

s.downstream(data)
	Entry point for upstream modules to push data downstream. If module is
	top module (like ``Application``) calling ``downstream`` will raise
	``ConfigError`` exception with ``S_ENODOWNLINK`` error.

s.send(data)
	Receive data from upper level for sending	

p.transmit(data)
	Translate internal message format to complete protocol message with proper
	message sequence numbers. Convert complete message to wire format. Called
	by ``s.send``

s.transmit(data)
	Called by ``p.transmit`` to enqueue data for actual transmission or passing
	it to lower level modules for handling.

t.send(data)
	Called by ``s.transmit`` to write data to transport. Alternatively could
	be called by ``s.event_writable`` to send data if session implements
	queueing for transmission. 

t.handle_write()
	Executed by event loop runner if session has data enqueued for sending
	and channel is able to receive data. 

s.event_writable(transport)
	Called by ``t.handle_write`` if channel is able to receive data.


t.writable()
	``Transport`` method for event loop runner to decide if channel availability
	for writing needs to be monitor and triggered.

s.writable()
	Called by ``t.writable`` to catch session level output triggering.	


Module Stack
------------
	::

	a.event_readable()				a.transmit()
	- t.recv()		    	  	  	- t.send()
	|						|
	a.recv()					p.transmit()
	|			APPLICATON		|
	p.received()		MODULE			a.send()
	|						|
	a.received()					a.upstream()
	|-----------------------------------------------|------------
	f.downstream()					f.received()
	|						|
	f.send()					p.received()
	|			FILTER			|
	p.transmit()		MODULE			f.recv()
	|						|
	f.transmit()					f.upstream()
	|------------------------------------------------------------
	s.downstream()					s.received()
	|						|
	s.send()					p.received()
	|			SESSION			|
	p.transmit()		MODULE			s.recv()
	|						|
	s.transmit()					s.event_readable()
	|						- t.recv()
	s.event_writable()
	- t.send()		TRANSPORT
