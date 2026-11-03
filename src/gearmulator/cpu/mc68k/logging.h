#pragma once

#include <sstream>
#include <string>
#include <iomanip>

namespace mc68k
{
	void logToConsole( const std::string& _s );
}

#ifdef MCLOG_ENABLED
#define MCLOG(S)																											\
do																															\
{																															\
	std::stringstream _ss_logging_cpp;	_ss_logging_cpp << __func__ << "@" << __LINE__ << ": " << S;						\
																															\
	mc68k::logToConsole(_ss_logging_cpp.str());																				\
}																															\
while(0)
#else
#define MCLOG(S) do { } while(0)
#endif

#define MCHEXN(S, n)		std::hex << std::setfill('0') << std::setw(n) << (uint32_t)S
#define MCHEX(S)			MCHEXN(S, 8)
